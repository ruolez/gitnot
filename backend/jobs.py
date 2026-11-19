"""Background jobs (imports, push mirrors), run by worker.py in their own
container so a web worker restart never cuts one short."""

import hashlib
import json
import os
import subprocess
import urllib.request
from datetime import datetime

import db
import gitcmd
import remotes
import repos

GITHUB_API = "https://api.github.com"
CHUNK = 1024 * 1024


def enqueue(kind, repo_id, payload=None, user_id=None, dedupe=False):
    """Queue a job. dedupe: skip when one of this kind is already queued for the repo."""
    if dedupe and db.query("SELECT 1 FROM jobs WHERE kind = %s AND repo_id = %s AND status = 'queued'",
                           (kind, repo_id), one=True):
        return None
    return db.execute(
        "INSERT INTO jobs (kind, repo_id, payload, created_by) VALUES (%s, %s, %s, %s) RETURNING *",
        (kind, repo_id, json.dumps(payload or {}), user_id), returning=True,
    )


def claim():
    return db.execute(
        """UPDATE jobs SET status = 'running', started_at = now()
           WHERE id = (SELECT id FROM jobs WHERE status = 'queued' ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1)
           RETURNING *""",
        returning=True,
    )


def progress(job_id, text):
    db.execute("UPDATE jobs SET progress = %s WHERE id = %s", (text[:500], job_id))


def finish(job_id, ok, message=""):
    # The payload may hold a token for the remote: it isn't needed any more.
    db.execute(
        """UPDATE jobs SET status = %s, message = %s, finished_at = now(), payload = payload - 'token'
           WHERE id = %s""",
        ("done" if ok else "failed", message[:2000], job_id),
    )


def recover_interrupted():
    """Jobs left 'running' by a worker that died can't be resumed safely."""
    db.execute("""UPDATE jobs SET status = 'failed', message = 'Interrupted (the worker restarted)',
                  finished_at = now(), payload = payload - 'token' WHERE status = 'running'""")


class JobError(Exception):
    pass


def _git(repo_id, args, env, timeout=3600):
    proc = subprocess.run(["git", "--git-dir", gitcmd.repo_path(repo_id), *args], capture_output=True,
                          timeout=timeout, env={**gitcmd._ENV, **env})
    if proc.returncode != 0:
        raise JobError(proc.stderr.decode("utf-8", "replace").strip()[-1500:] or f"git {args[0]} failed")
    return proc.stdout.decode("utf-8", "replace")


def _github(path, token, accept="application/vnd.github+json"):
    req = urllib.request.Request(f"{GITHUB_API}{path}", headers={
        "Accept": accept, "User-Agent": "mygit-import", "X-GitHub-Api-Version": "2022-11-28",
        **({"Authorization": f"Bearer {token}"} if token else {}),
    })
    return urllib.request.urlopen(req, timeout=120)


def _github_json(path, token):
    try:
        with _github(path, token) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise JobError(f"GitHub API {path}: {e.code} {e.reason}") from None


def run_import(job):
    payload = job["payload"]
    repo = repos.get(job["repo_id"])
    internal = remotes.internal_allowed()
    url = remotes.check_remote_url(payload["url"], allow_internal=internal)
    env = remotes.git_env(payload.get("username"), payload.get("token"), allow_http=internal)
    progress(job["id"], "Fetching branches and tags…")
    head = _git(repo["id"], ["ls-remote", "--symref", url, "HEAD"], env, timeout=120)
    default = next((line.split()[1][len("refs/heads/"):] for line in head.splitlines()
                    if line.startswith("ref: refs/heads/")), None)
    # Branches and tags only: a GitHub mirror clone would also copy every pull request ref.
    _git(repo["id"], ["fetch", "--quiet", "--prune", "--no-write-fetch-head", url,
                      "+refs/heads/*:refs/heads/*", "+refs/tags/*:refs/tags/*"], env)
    branches = gitcmd.branches(repo["id"])
    if not branches:
        raise JobError("The remote has no branches")
    default = default if default in branches else ("main" if "main" in branches else sorted(branches)[0])
    gitcmd.set_head(repo["id"], default)
    db.execute(
        """UPDATE repos SET default_branch = %s, is_empty = false, size_kb = %s, pushed_at = now(),
                  updated_at = now() WHERE id = %s""",
        (default, gitcmd.size_kb(repo["id"]), repo["id"]),
    )
    summary = f"Imported {len(branches)} branch{'es' if len(branches) != 1 else ''}"
    tags = gitcmd.text(repo["id"], ["for-each-ref", "--format=%(refname)", "refs/tags/"]).split()
    summary += f" and {len(tags)} tag{'s' if len(tags) != 1 else ''}"
    mode = payload.get("releases", "none")
    gh = remotes.github_repo(url)
    if mode != "none" and gh:
        count, files = import_github_releases(job, repo, gh, payload.get("token"), latest_only=mode == "latest")
        summary += f", {count} release{'s' if count != 1 else ''} with {files} file{'s' if files != 1 else ''}"
    return summary


def _parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def import_github_releases(job, repo, gh, token, latest_only=False):
    import releases_api

    owner, name = gh
    latest = _github_json(f"/repos/{owner}/{name}/releases/latest", token)
    if latest_only:
        found = [latest] if latest else []
    else:
        found = []
        for page in range(1, 51):
            batch = _github_json(f"/repos/{owner}/{name}/releases?per_page=100&page={page}", token) or []
            found.extend(batch)
            if len(batch) < 100:
                break
    flags = remotes.latest_flags(found, latest["tag_name"] if latest else None)
    files = 0
    for i, r in enumerate(found, 1):
        if r.get("draft"):
            continue
        progress(job["id"], f"Release {i}/{len(found)}: {r['tag_name']}")
        if db.query("SELECT 1 FROM releases WHERE repo_id = %s AND tag_name = %s", (repo["id"], r["tag_name"]),
                    one=True):
            continue
        row = db.execute(
            """INSERT INTO releases (repo_id, tag_name, target_commitish, name, body, draft, prerelease,
                                     make_latest, created_by, created_at, published_at)
               VALUES (%s, %s, %s, %s, %s, false, %s, %s, %s, %s, %s) RETURNING *""",
            (repo["id"], r["tag_name"], r.get("target_commitish") or "", r.get("name") or "", r.get("body") or "",
             bool(r.get("prerelease")), flags.get(r["tag_name"], True), job["created_by"],
             _parse_time(r.get("created_at")) or datetime.now(), _parse_time(r.get("published_at"))),
            returning=True,
        )
        os.makedirs(releases_api.releases_dir(repo["id"]), exist_ok=True)
        for a in r.get("assets") or []:
            progress(job["id"], f"Release {i}/{len(found)}: {r['tag_name']}: {a['name']}")
            asset = db.execute(
                """INSERT INTO release_assets (release_id, name, label, content_type, size, sha256, uploaded_by,
                                               uploader, download_count)
                   VALUES (%s, %s, %s, %s, 0, '', %s, %s, %s) RETURNING *""",
                (row["id"], a["name"], a.get("label") or "", a.get("content_type") or "application/octet-stream",
                 job["created_by"], (a.get("uploader") or {}).get("login", ""), a.get("download_count") or 0),
                returning=True,
            )
            path = releases_api.asset_path(repo["id"], asset["id"])
            digest, size = hashlib.sha256(), 0
            with _github(f"/repos/{owner}/{name}/releases/assets/{a['id']}", token,
                         accept="application/octet-stream") as resp, open(path, "wb") as f:
                while True:
                    chunk = resp.read(CHUNK)
                    if not chunk:
                        break
                    digest.update(chunk)
                    size += len(chunk)
                    f.write(chunk)
            db.execute("UPDATE release_assets SET size = %s, sha256 = %s WHERE id = %s",
                       (size, digest.hexdigest(), asset["id"]))
            files += 1
    return len([r for r in found if not r.get("draft")]), files


def run_mirror(job):
    mirror = db.query("SELECT * FROM push_mirrors WHERE repo_id = %s", (job["repo_id"],), one=True)
    if not mirror or not mirror["enabled"]:
        return "Mirror is off"
    try:
        internal = remotes.internal_allowed()
        url = remotes.check_remote_url(mirror["url"], allow_internal=internal)
        env = remotes.git_env(mirror["username"], mirror["token"], allow_http=internal)
        _git(job["repo_id"], ["push", "--quiet", "--prune", "--porcelain", url, "+refs/heads/*:refs/heads/*",
                              "+refs/tags/*:refs/tags/*"], env)
    except (JobError, remotes.RemoteError, subprocess.TimeoutExpired) as e:
        db.execute("UPDATE push_mirrors SET last_at = now(), last_status = 'failed', last_error = %s WHERE repo_id = %s",
                   (str(e)[:2000], job["repo_id"]))
        raise
    db.execute("UPDATE push_mirrors SET last_at = now(), last_status = 'ok', last_error = '' WHERE repo_id = %s",
               (job["repo_id"],))
    return "Pushed branches and tags"


RUNNERS = {"import": run_import, "mirror": run_mirror}


def run(job):
    try:
        message = RUNNERS[job["kind"]](job)
    except Exception as e:  # noqa: BLE001 - every failure is reported on the job
        finish(job["id"], False, str(e) or e.__class__.__name__)
        return False
    finish(job["id"], True, message or "")
    return True
