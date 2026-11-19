"""Endpoints for the other containers, never for browsers: nginx's
auth_request for git over HTTPS, the git hooks, and (later) sshd.
Every call carries X-Internal-Token; nginx doesn't route /internal/ publicly."""

import hmac
from functools import wraps

from flask import Blueprint, Response, g, jsonify, request

import config
import credentials
import db
import gitcmd
import repos
import urls
from auth import record_failure, too_many_failures
from git_auth import decide, error_advertisement, parse_git_request
from permissions import at_least, can_push
from util import body

bp = Blueprint("internal", __name__, url_prefix="/internal")

DEFAULT_MAX_FILE_MB = 100


def internal_only(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        given = request.headers.get("X-Internal-Token", "")
        if not hmac.compare_digest(given.encode(), config.INTERNAL_TOKEN.encode()):
            return Response("forbidden\n", 403, mimetype="text/plain")
        return f(*args, **kwargs)

    return wrapper


def _judge():
    """(decision, req, repo, principal) for the git request nginx is asking about."""
    from git_auth import Decision

    uri = request.headers.get("X-Original-URI", "")
    req = parse_git_request(uri)
    if req is None:
        return Decision(403, "Not a git request"), None, None, None
    principal = credentials.ANONYMOUS
    header = request.headers.get("Authorization", "")
    token = credentials.parse_authorization(header) if header else None
    if header:
        ip = request.headers.get("X-Real-IP", "")
        principal = credentials.lookup(token) if token else None
        if principal is None:
            if too_many_failures(ip, "token"):
                return Decision(403, "Too many failed sign-ins from your address; try again later"), req, None, None
            record_failure(ip, "token")
            return Decision(401, "Bad credentials"), req, None, None
    repo = repos.resolve(req.owner, req.repo)
    level = repos.access_for(repo, principal)
    return decide(req, repo, level, principal is not credentials.ANONYMOUS), req, repo, principal


@bp.get("/git-auth")
@internal_only
def git_auth():
    decision, req, repo, principal = _judge()
    if decision.status == 401:
        return Response("", 401, {"WWW-Authenticate": 'Basic realm="mygit"'})
    if decision.status != 200:
        return Response("", 403)
    user = principal.user
    return Response("", 200, {
        "X-Mygit-Path": f"/{repo['id']}.git/{req.endpoint}",
        "X-Mygit-Repo-Id": str(repo["id"]),
        "X-Mygit-User": principal.username,
        "X-Mygit-User-Id": str(user["id"]) if user else "",
        "X-Mygit-Token-Kind": principal.kind,
    })


@bp.route("/git-denied", methods=["GET", "POST"])
@internal_only
def git_denied():
    """nginx sends refused git requests here (error_page 403) so the git
    client prints the reason, as GitHub's 'Repository not found.'"""
    decision, req, _repo, _principal = _judge()
    message = decision.message or "Access denied"
    if req is not None and req.endpoint == "info/refs":
        return Response(error_advertisement(req.service, message), 200,
                        {"Content-Type": f"application/x-{req.service}-advertisement",
                         "Cache-Control": "no-cache"})
    return Response(message + "\n", 403, mimetype="text/plain")


def _hook_context(data):
    repo = repos.get(int(data.get("repo_id") or 0))
    user = None
    if data.get("user_id"):
        user = db.query("SELECT * FROM users WHERE id = %s AND is_active", (int(data["user_id"]),), one=True)
    return repo, user


def _updates(data):
    out = []
    for u in data.get("refs") or []:
        old, new, ref = str(u.get("old", "")), str(u.get("new", "")), str(u.get("ref", ""))
        if len(old) == 40 and len(new) == 40 and ref.startswith("refs/"):
            out.append({"old": old, "new": new, "ref": ref})
    return out


@bp.post("/hooks/pre-receive")
@internal_only
def pre_receive():
    import protection

    data = body()
    repo, user = _hook_context(data)
    if repo is None:
        return jsonify({"ok": False, "messages": ["Repository not found"]})
    if repo["archived"]:
        return jsonify({"ok": False, "messages": ["This repository is archived and read-only"]})
    # The push was authorized when it started; deploy tokens have no user and were
    # checked by nginx/sshd. A user deactivated since then is refused here.
    if data.get("user_id") and user is None:
        return jsonify({"ok": False, "messages": ["Your account is not active"]})
    level = "write"
    if user is not None:
        level = repos.access_for(repo, credentials.Principal(user=user, access=data.get("token_access") or "admin",
                                                             kind="personal"))
        if not can_push(repo, level):
            return jsonify({"ok": False, "messages": ["You no longer have write access"]})
    problems = protection.check(repo, level, _updates(data), is_force=data.get("force") or {})
    max_mb = int(db.get_setting("max_file_mb", DEFAULT_MAX_FILE_MB))
    return jsonify({"ok": not problems, "messages": problems, "max_file_mb": max_mb})


@bp.post("/hooks/post-receive")
@internal_only
def post_receive():
    data = body()
    repo, user = _hook_context(data)
    if repo is None:
        return jsonify({"messages": []})
    updates = _updates(data)
    actor = str(data.get("actor") or (user["username"] if user else ""))[:100]
    via = "ssh" if data.get("via") == "ssh" else "http"
    messages = []
    with db.transaction():
        for u in updates:
            db.execute(
                """INSERT INTO push_events (repo_id, user_id, actor, via, ref, old_sha, new_sha)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (repo["id"], user["id"] if user else None, actor, via, u["ref"], u["old"], u["new"]),
            )
        pushed = [u["ref"][len("refs/heads/"):] for u in updates
                  if u["ref"].startswith("refs/heads/") and u["new"] != gitcmd.ZERO_SHA]
        default_branch = fix_head(repo, pushed)
        branches = gitcmd.branches(repo["id"])
        db.execute(
            """UPDATE repos SET pushed_at = now(), updated_at = now(), is_empty = %s, size_kb = %s,
                      default_branch = %s WHERE id = %s""",
            (not branches, gitcmd.size_kb(repo["id"]), default_branch, repo["id"]),
        )
    if repo["is_empty"] and branches and urls.base_url():
        messages.append(f"View it at {urls.base_url()}{urls.repo_path(repo['owner'], repo['name'])}")
    return jsonify({"messages": messages})


def fix_head(repo, pushed_branches):
    """Point HEAD at a branch that exists. A new repository's HEAD names its
    default branch; if the first push brings only `master`, HEAD would dangle
    and clones would check out nothing. Returns the default branch name."""
    current = gitcmd.head_branch(repo["id"]) or repo["default_branch"]
    if gitcmd.ref_exists(repo["id"], f"refs/heads/{current}"):
        return current
    existing = gitcmd.branches(repo["id"])
    if not existing:
        return current
    choice = next((b for b in pushed_branches if b in existing), None) or sorted(existing)[0]
    gitcmd.set_head(repo["id"], choice)
    return choice
