"""Importing repositories from other servers, push mirrors, and the job list."""

from flask import Blueprint, g, jsonify

import db
import jobs
import remotes
import repos
from auth import session_required, login_required
from names import repo_name_error
from repos_api import load_repo, repo_json
from util import api_error, audit, body

bp = Blueprint("import", __name__, url_prefix="/api")


def job_json(j):
    return {"id": j["id"], "kind": j["kind"], "status": j["status"], "progress": j["progress"],
            "message": j["message"], "created_at": j["created_at"].isoformat(),
            "finished_at": j["finished_at"].isoformat() if j["finished_at"] else None}


@bp.post("/repos/import")
@session_required
def import_repo():
    data = body()
    try:
        url = remotes.check_remote_url(data.get("url"), allow_internal=remotes.internal_allowed())
    except remotes.RemoteError as e:
        return api_error(str(e))
    gh = remotes.github_repo(url)
    name = str(data.get("name") or (gh[1] if gh else url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git"))).strip()
    err = repo_name_error(name)
    if err:
        return api_error(err)
    owner = g.user
    if data.get("owner") and data["owner"].lower() != g.user["username"].lower():
        if not g.user["is_admin"]:
            return api_error("You can only import into your own account", 403)
        owner = db.query("SELECT * FROM users WHERE lower(username) = lower(%s)", (data["owner"],), one=True)
        if not owner:
            return api_error("No such user", 404)
    if repos.find(owner["username"], name):
        return api_error(f"{owner['username']}/{name} already exists", 409)
    mode = data.get("releases", "none")
    if mode not in ("none", "latest", "all"):
        return api_error("releases must be none, latest or all")
    repo = repos.create(owner["id"], name, str(data.get("description") or "")[:500], bool(data.get("private")))
    job = jobs.enqueue("import", repo["id"], {"url": url, "token": str(data.get("token") or ""),
                                              "username": str(data.get("username") or ""), "releases": mode},
                       g.user["id"])
    audit("repo.import_started", {"repo": f"{repo['owner']}/{repo['name']}", "url": url, "releases": mode})
    return jsonify({"repo": repo_json(repo, "admin"), "job": job_json(job)}), 201


@bp.get("/repos/<owner>/<name>/jobs")
@login_required
def list_jobs(owner, name):
    found, err = load_repo(owner, name)
    if err:
        return err
    repo, _ = found
    rows = db.query("SELECT * FROM jobs WHERE repo_id = %s ORDER BY id DESC LIMIT 20", (repo["id"],))
    return jsonify([job_json(j) for j in rows])


def mirror_json(m):
    if not m:
        return None
    return {"url": m["url"], "username": m["username"], "has_token": bool(m["token"]), "enabled": m["enabled"],
            "last_at": m["last_at"].isoformat() if m["last_at"] else None, "last_status": m["last_status"],
            "last_error": m["last_error"]}


@bp.get("/repos/<owner>/<name>/mirror")
@session_required
def get_mirror(owner, name):
    found, err = load_repo(owner, name, "admin")
    if err:
        return err
    repo, _ = found
    return jsonify(mirror_json(db.query("SELECT * FROM push_mirrors WHERE repo_id = %s", (repo["id"],), one=True)))


@bp.put("/repos/<owner>/<name>/mirror")
@session_required
def put_mirror(owner, name):
    found, err = load_repo(owner, name, "admin")
    if err:
        return err
    repo, _ = found
    data = body()
    try:
        url = remotes.check_remote_url(data.get("url"), allow_internal=remotes.internal_allowed())
    except remotes.RemoteError as e:
        return api_error(str(e))
    current = db.query("SELECT * FROM push_mirrors WHERE repo_id = %s", (repo["id"],), one=True)
    token = data.get("token")
    if token is None or token == "":
        token = current["token"] if current else ""
    db.execute(
        """INSERT INTO push_mirrors (repo_id, url, username, token, enabled) VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (repo_id) DO UPDATE SET url = EXCLUDED.url, username = EXCLUDED.username,
               token = EXCLUDED.token, enabled = EXCLUDED.enabled""",
        (repo["id"], url, str(data.get("username") or "x-access-token")[:100], str(token), data.get("enabled", True) is not False),
    )
    audit("mirror.set", {"repo": f"{repo['owner']}/{repo['name']}", "url": url})
    if not repo["is_empty"]:
        jobs.enqueue("mirror", repo["id"], user_id=g.user["id"], dedupe=True)
    return jsonify(mirror_json(db.query("SELECT * FROM push_mirrors WHERE repo_id = %s", (repo["id"],), one=True)))


@bp.delete("/repos/<owner>/<name>/mirror")
@session_required
def delete_mirror(owner, name):
    found, err = load_repo(owner, name, "admin")
    if err:
        return err
    repo, _ = found
    db.execute("DELETE FROM push_mirrors WHERE repo_id = %s", (repo["id"],))
    audit("mirror.removed", {"repo": f"{repo['owner']}/{repo['name']}"})
    return jsonify({"ok": True})


@bp.post("/repos/<owner>/<name>/mirror/sync")
@session_required
def sync_mirror(owner, name):
    found, err = load_repo(owner, name, "admin")
    if err:
        return err
    repo, _ = found
    if not db.query("SELECT 1 FROM push_mirrors WHERE repo_id = %s AND enabled", (repo["id"],), one=True):
        return api_error("No mirror is set up", 404)
    job = jobs.enqueue("mirror", repo["id"], user_id=g.user["id"], dedupe=True)
    return jsonify({"queued": job is not None})


def import_running(repo_id):
    return db.query("SELECT 1 FROM jobs WHERE kind = 'import' AND repo_id = %s AND status IN ('queued', 'running')",
                    (repo_id,), one=True) is not None
