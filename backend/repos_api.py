from flask import Blueprint, g, jsonify, request

import db
import gitcmd
import repos
import urls
from auth import login_required
from names import repo_name_error
from permissions import at_least
from util import api_error, audit, body

bp = Blueprint("repos", __name__, url_prefix="/api")

VISIBLE_SQL = """(NOT r.is_private
    OR %(uid)s::bigint IS NOT NULL AND (r.owner_id = %(uid)s OR %(admin)s
        OR EXISTS (SELECT 1 FROM collaborators c WHERE c.repo_id = r.id AND c.user_id = %(uid)s)))"""


def _visibility_params():
    user = g.user
    if g.principal.kind == "deploy":
        return {"uid": None, "admin": False}
    return {"uid": user["id"] if user else None, "admin": bool(user and user["is_admin"])}


def load_repo(owner, name, wanted="read"):
    """(repo, level) when the caller has `wanted` access, else (None, error response).
    Repositories the caller can't see are reported as missing."""
    repo = repos.find(owner, name)
    if repo is None:
        repo = repos.find_redirect(owner, name)
    level = repos.access_for(repo, g.principal)
    if repo is None or not at_least(level, "read"):
        return None, api_error("Repository not found", 404)
    if not at_least(level, wanted):
        return None, api_error(f"You need {wanted} access to do this", 403)
    return (repo, level), None


def repo_json(repo, level):
    out = repos.public_repo(repo, level)
    out["clone_urls"] = urls.clone_urls(repo["owner"], repo["name"])
    out["html_url"] = urls.base_url() + urls.repo_path(repo["owner"], repo["name"])
    return out


@bp.post("/repos")
@login_required
def create_repo():
    data = body()
    name = str(data.get("name") or "").strip()
    err = repo_name_error(name)
    if err:
        return api_error(err)
    owner = g.user
    if data.get("owner") and data["owner"].lower() != g.user["username"].lower():
        if not g.user["is_admin"]:
            return api_error("You can only create repositories for yourself", 403)
        owner = db.query("SELECT * FROM users WHERE lower(username) = lower(%s)", (data["owner"],), one=True)
        if not owner:
            return api_error("No such user", 404)
    branch = str(data.get("default_branch") or "main").strip()
    if gitcmd.run(None, ["check-ref-format", "--branch", branch], check=False).strip() != branch.encode() \
            or branch.startswith("-"):
        return api_error("That is not a valid branch name")
    if repos.find(owner["username"], name):
        return api_error(f"{owner['username']}/{name} already exists", 409)
    repo = repos.create(owner["id"], name, str(data.get("description") or "")[:500],
                        bool(data.get("private")), branch)
    audit("repo.created", {"repo": f"{repo['owner']}/{repo['name']}", "private": repo["is_private"]})
    return jsonify(repo_json(repo, "admin")), 201


@bp.get("/repos/<owner>/<name>")
def get_repo(owner, name):
    found, err = load_repo(owner, name)
    if err:
        return err
    repo, level = found
    return jsonify(repo_json(repo, level))


@bp.delete("/repos/<owner>/<name>")
@login_required
def delete_repo(owner, name):
    found, err = load_repo(owner, name, "admin")
    if err:
        return err
    repo, _ = found
    if g.principal.kind != "session":
        return api_error("Delete repositories on the website", 403)
    repos.delete(repo["id"])
    audit("repo.deleted", {"repo": f"{repo['owner']}/{repo['name']}"})
    return jsonify({"ok": True})


def _list(where, params, limit=200):
    p = {**_visibility_params(), **params, "limit": limit}
    rows = db.query(
        f"""SELECT {repos.REPO_COLUMNS} FROM repos r JOIN users u ON u.id = r.owner_id
            WHERE {VISIBLE_SQL} AND {where}
            ORDER BY COALESCE(r.pushed_at, r.created_at) DESC LIMIT %(limit)s""",
        p,
    )
    return [repos.public_repo(r) for r in rows]


@bp.get("/repos")
@login_required
def my_repos():
    """Repositories the caller owns or collaborates on."""
    return jsonify(_list(
        "(r.owner_id = %(me)s OR EXISTS (SELECT 1 FROM collaborators c WHERE c.repo_id = r.id AND c.user_id = %(me)s))",
        {"me": g.user["id"]},
    ))


@bp.get("/explore")
def explore():
    q = str(request.args.get("q") or "").strip()[:100]
    if q:
        return jsonify(_list("(r.name ILIKE %(q)s OR r.description ILIKE %(q)s OR u.username ILIKE %(q)s)",
                             {"q": f"%{q.replace('%', '').replace('_', '')}%"}))
    return jsonify(_list("true", {}))


@bp.get("/users/<username>")
def user_profile(username):
    user = db.query("SELECT * FROM users WHERE lower(username) = lower(%s) AND is_active", (username,), one=True)
    if not user:
        return api_error("No such user", 404)
    return jsonify({
        "username": user["username"],
        "full_name": user["full_name"],
        "created_at": user["created_at"].isoformat(),
        "repos": _list("r.owner_id = %(owner)s", {"owner": user["id"]}),
    })


@bp.get("/activity")
@login_required
def activity():
    """Recent pushes to repositories the caller can see."""
    rows = db.query(
        f"""SELECT p.ref, p.old_sha, p.new_sha, p.at, p.actor, p.via, u.username AS owner, r.name
            FROM push_events p JOIN repos r ON r.id = p.repo_id JOIN users u ON u.id = r.owner_id
            WHERE {VISIBLE_SQL}
            ORDER BY p.at DESC LIMIT 30""",
        _visibility_params(),
    )
    return jsonify([{
        "repo": f"{r['owner']}/{r['name']}", "ref": r["ref"], "old_sha": r["old_sha"], "new_sha": r["new_sha"],
        "at": r["at"].isoformat(), "actor": r["actor"], "via": r["via"],
    } for r in rows])
