"""Releases over a GitHub-compatible REST API (/api/v1/repos/<owner>/<repo>/releases...)
and downloads at /<owner>/<repo>/releases/download/<tag>/<asset>."""

import hashlib
import mimetypes
import os
import shutil
import uuid

from flask import Blueprint, Response, g, jsonify, request

import config
import db
import gitcmd
import repos
import urls
from browse_api import resolve_commit
from markdown_render import render_markdown
from permissions import at_least, can_push
from releases import asset_name_error, pick_latest, release_json, tag_name_error
from repos_api import load_repo
from util import api_error, audit, body

bp = Blueprint("releases", __name__)
API = "/api/v1/repos/<owner>/<name>"
CHUNK = 1024 * 1024


def releases_dir(repo_id):
    return os.path.join(config.RELEASES_DIR, str(int(repo_id)))


def asset_path(repo_id, asset_id):
    return os.path.join(releases_dir(repo_id), str(int(asset_id)))


def _full(repo):
    return f"{repo['owner']}/{repo['name']}"


def _assets(release_ids):
    if not release_ids:
        return {}
    rows = db.query("SELECT * FROM release_assets WHERE release_id = ANY(%s) ORDER BY name", (list(release_ids),))
    out = {}
    for a in rows:
        out.setdefault(a["release_id"], []).append(a)
    return out


def _authors(releases):
    ids = [r["created_by"] for r in releases if r["created_by"]]
    if not ids:
        return {}
    return {u["id"]: u["username"] for u in db.query("SELECT id, username FROM users WHERE id = ANY(%s)", (ids,))}


def to_json(repo, rows, with_html=False):
    assets = _assets([r["id"] for r in rows])
    authors = _authors(rows)
    out = []
    for r in rows:
        item = release_json(r, assets.get(r["id"], []), urls.base_url(), _full(repo), authors.get(r["created_by"], ""))
        if with_html:
            item["body_html"] = render_markdown(r["body"], repo["owner"], repo["name"], r["tag_name"])
        out.append(item)
    return out


def visible_releases(repo, level):
    rows = db.query("SELECT * FROM releases WHERE repo_id = %s ORDER BY COALESCE(published_at, created_at) DESC, id DESC",
                    (repo["id"],))
    if not at_least(level, "write"):
        rows = [r for r in rows if not r["draft"]]
    return rows


def _load(owner, name, wanted="read"):
    found, err = load_repo(owner, name, wanted)
    if err:
        return None, None, err
    repo, level = found
    if wanted == "write" and not can_push(repo, level):
        return None, None, api_error("This repository is archived and read-only", 403)
    return repo, level, None


def _release(repo, level, release_id=None, tag=None):
    if release_id is not None:
        row = db.query("SELECT * FROM releases WHERE id = %s AND repo_id = %s", (release_id, repo["id"]), one=True)
    else:
        row = db.query("SELECT * FROM releases WHERE tag_name = %s AND repo_id = %s", (tag, repo["id"]), one=True)
    if row is None or (row["draft"] and not at_least(level, "write")):
        return None
    return row


def ensure_tag(repo, tag, target):
    """Create a lightweight tag at `target` (branch or sha) if it is missing.
    Returns an error message or None."""
    ref = f"refs/tags/{tag}"
    if gitcmd.ref_exists(repo["id"], ref):
        return None
    sha = resolve_commit(repo["id"], target or repo["default_branch"])
    if sha is None:
        return f"Can't create tag {tag}: no branch or commit {target or repo['default_branch']!r}"
    gitcmd.run(repo["id"], ["update-ref", ref, sha, gitcmd.ZERO_SHA])
    import internal_api

    internal_api.record_push(repo, g.user, "web", [{"old": gitcmd.ZERO_SHA, "new": sha, "ref": ref}],
                             actor=g.principal.username)
    return None


# ---------- REST API ----------

@bp.get(f"{API}/releases")
def list_releases(owner, name):
    repo, level, err = _load(owner, name)
    if err:
        return err
    per_page = max(1, min(int(request.args.get("per_page", 30) or 30), 100))
    page = max(1, int(request.args.get("page", 1) or 1))
    rows = visible_releases(repo, level)[(page - 1) * per_page: page * per_page]
    return jsonify(to_json(repo, rows, with_html=request.args.get("html") == "1"))


@bp.get(f"{API}/releases/latest")
def latest_release(owner, name):
    repo, level, err = _load(owner, name)
    if err:
        return err
    row = pick_latest(visible_releases(repo, level))
    if row is None:
        return api_error("Not Found", 404)
    return jsonify(to_json(repo, [row])[0])


@bp.get(f"{API}/releases/tags/<path:tag>")
def release_by_tag(owner, name, tag):
    repo, level, err = _load(owner, name)
    if err:
        return err
    row = _release(repo, level, tag=tag)
    if row is None:
        return api_error("Not Found", 404)
    return jsonify(to_json(repo, [row], with_html=request.args.get("html") == "1")[0])


@bp.get(f"{API}/releases/<int:release_id>")
def get_release(owner, name, release_id):
    repo, level, err = _load(owner, name)
    if err:
        return err
    row = _release(repo, level, release_id)
    if row is None:
        return api_error("Not Found", 404)
    return jsonify(to_json(repo, [row], with_html=request.args.get("html") == "1")[0])


def _release_fields(data, partial):
    fields = {}
    if not partial or "tag_name" in data:
        tag = str(data.get("tag_name") or "").strip()
        err = tag_name_error(tag)
        if err:
            raise ValueError(err)
        fields["tag_name"] = tag
    for key, limit in (("name", 200), ("body", 100000), ("target_commitish", 200)):
        if key in data:
            fields[key] = str(data[key] or "")[:limit]
    for key in ("draft", "prerelease"):
        if key in data:
            fields[key] = bool(data[key])
    if "make_latest" in data:
        fields["make_latest"] = str(data["make_latest"]).lower() not in ("false", "0")
    return fields


@bp.post(f"{API}/releases")
def create_release(owner, name):
    repo, level, err = _load(owner, name, "write")
    if err:
        return err
    try:
        fields = _release_fields(body(), partial=False)
    except ValueError as e:
        return api_error(str(e), 422)
    if db.query("SELECT 1 FROM releases WHERE repo_id = %s AND tag_name = %s", (repo["id"], fields["tag_name"]),
                one=True):
        return api_error(f"A release for {fields['tag_name']} already exists", 422, code="already_exists")
    if repo["is_empty"]:
        return api_error("Push some code before making a release", 422)
    fields.setdefault("target_commitish", repo["default_branch"])
    if not fields.get("draft"):
        problem = ensure_tag(repo, fields["tag_name"], fields["target_commitish"])
        if problem:
            return api_error(problem, 422)
    cols = {**fields, "repo_id": repo["id"], "created_by": g.user["id"] if g.user else None}
    placeholders = ", ".join(["%s"] * len(cols))
    row = db.execute(
        f"INSERT INTO releases ({', '.join(cols)}, published_at) VALUES ({placeholders}, "
        f"{'NULL' if fields.get('draft') else 'now()'}) RETURNING *",
        tuple(cols.values()), returning=True,
    )
    audit("release.created", {"repo": _full(repo), "tag": row["tag_name"], "draft": row["draft"]})
    return jsonify(to_json(repo, [row])[0]), 201


@bp.patch(f"{API}/releases/<int:release_id>")
def update_release(owner, name, release_id):
    repo, level, err = _load(owner, name, "write")
    if err:
        return err
    row = _release(repo, level, release_id)
    if row is None:
        return api_error("Not Found", 404)
    try:
        fields = _release_fields(body(), partial=True)
    except ValueError as e:
        return api_error(str(e), 422)
    if "tag_name" in fields and fields["tag_name"] != row["tag_name"]:
        if db.query("SELECT 1 FROM releases WHERE repo_id = %s AND tag_name = %s AND id <> %s",
                    (repo["id"], fields["tag_name"], release_id), one=True):
            return api_error(f"A release for {fields['tag_name']} already exists", 422, code="already_exists")
    publishing = row["draft"] and fields.get("draft") is False
    tag = fields.get("tag_name", row["tag_name"])
    if not fields.get("draft", row["draft"]):
        problem = ensure_tag(repo, tag, fields.get("target_commitish", row["target_commitish"]))
        if problem:
            return api_error(problem, 422)
    if fields:
        sets = ", ".join(f"{k} = %s" for k in fields)
        extra = ", published_at = now()" if publishing else ""
        row = db.execute(f"UPDATE releases SET {sets}{extra} WHERE id = %s RETURNING *",
                         (*fields.values(), release_id), returning=True)
    audit("release.updated", {"repo": _full(repo), "tag": row["tag_name"], "published": publishing})
    return jsonify(to_json(repo, [row])[0])


@bp.delete(f"{API}/releases/<int:release_id>")
def delete_release(owner, name, release_id):
    repo, level, err = _load(owner, name, "write")
    if err:
        return err
    row = _release(repo, level, release_id)
    if row is None:
        return api_error("Not Found", 404)
    assets = db.query("SELECT id FROM release_assets WHERE release_id = %s", (release_id,))
    db.execute("DELETE FROM releases WHERE id = %s", (release_id,))
    for a in assets:
        try:
            os.remove(asset_path(repo["id"], a["id"]))
        except FileNotFoundError:
            pass
    audit("release.deleted", {"repo": _full(repo), "tag": row["tag_name"]})
    return Response(status=204)


def _content_type(name, given):
    if given and given not in ("application/x-www-form-urlencoded", "multipart/form-data") and "/" in given:
        return given.split(";")[0].strip()[:100]
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


@bp.post(f"{API}/releases/<int:release_id>/assets")
def upload_asset(owner, name, release_id):
    """Raw request body = the file (as GitHub's uploads endpoint): ?name=app.zip"""
    repo, level, err = _load(owner, name, "write")
    if err:
        return err
    row = _release(repo, level, release_id)
    if row is None:
        return api_error("Not Found", 404)
    asset_name = request.args.get("name", "")
    problem = asset_name_error(asset_name)
    if problem:
        return api_error(problem, 422)
    if db.query("SELECT 1 FROM release_assets WHERE release_id = %s AND name = %s", (release_id, asset_name),
                one=True):
        return api_error(f"{asset_name} is already attached to this release", 422, code="already_exists")
    limit = int(db.get_setting("max_asset_mb", "2048")) * 1024 * 1024
    if request.content_length is not None and request.content_length > limit:
        return api_error(f"Assets can be at most {limit // 1048576} MB", 413)
    os.makedirs(releases_dir(repo["id"]), exist_ok=True)
    tmp = os.path.join(releases_dir(repo["id"]), f".upload-{uuid.uuid4().hex}")
    digest = hashlib.sha256()
    size = 0
    try:
        with open(tmp, "wb") as f:
            while True:
                chunk = request.stream.read(CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise OverflowError
                digest.update(chunk)
                f.write(chunk)
        if request.content_length is not None and size != request.content_length:
            raise ConnectionError
    except OverflowError:
        os.remove(tmp)
        return api_error(f"Assets can be at most {limit // 1048576} MB", 413)
    except (ConnectionError, OSError):
        if os.path.exists(tmp):
            os.remove(tmp)
        return api_error("The upload was cut off", 400)
    if size == 0:
        os.remove(tmp)
        return api_error("The file is empty", 422)
    asset = db.execute(
        """INSERT INTO release_assets (release_id, name, label, content_type, size, sha256, uploaded_by, uploader)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
        (release_id, asset_name, str(request.args.get("label", ""))[:200],
         _content_type(asset_name, request.content_type), size, digest.hexdigest(),
         g.user["id"] if g.user else None, g.principal.username),
        returning=True,
    )
    os.replace(tmp, asset_path(repo["id"], asset["id"]))
    audit("release.asset_uploaded", {"repo": _full(repo), "tag": row["tag_name"], "asset": asset_name, "size": size})
    from releases import asset_json

    return jsonify(asset_json(asset, urls.base_url(), _full(repo), row["tag_name"])), 201


def _asset_row(repo, level, asset_id):
    a = db.query(
        """SELECT a.*, r.tag_name, r.draft FROM release_assets a JOIN releases r ON r.id = a.release_id
           WHERE a.id = %s AND r.repo_id = %s""", (asset_id, repo["id"]), one=True)
    if a is None or (a["draft"] and not at_least(level, "write")):
        return None
    return a


@bp.get(f"{API}/releases/assets/<int:asset_id>")
def get_asset(owner, name, asset_id):
    """JSON, or the file itself with Accept: application/octet-stream (GitHub's
    way of downloading assets of private repositories with a token)."""
    repo, level, err = _load(owner, name)
    if err:
        return err
    a = _asset_row(repo, level, asset_id)
    if a is None:
        return api_error("Not Found", 404)
    if "application/octet-stream" in (request.headers.get("Accept") or ""):
        return send_asset(repo, a)
    from releases import asset_json

    return jsonify(asset_json(a, urls.base_url(), _full(repo), a["tag_name"]))


@bp.delete(f"{API}/releases/assets/<int:asset_id>")
def delete_asset(owner, name, asset_id):
    repo, level, err = _load(owner, name, "write")
    if err:
        return err
    a = _asset_row(repo, level, asset_id)
    if a is None:
        return api_error("Not Found", 404)
    db.execute("DELETE FROM release_assets WHERE id = %s", (asset_id,))
    try:
        os.remove(asset_path(repo["id"], asset_id))
    except FileNotFoundError:
        pass
    audit("release.asset_deleted", {"repo": _full(repo), "tag": a["tag_name"], "asset": a["name"]})
    return Response(status=204)


# ---------- downloads ----------

def send_asset(repo, asset):
    """Hand the file to nginx (X-Accel-Redirect): it streams it and handles
    Range requests, so interrupted downloads resume."""
    db.execute("UPDATE release_assets SET download_count = download_count + 1 WHERE id = %s", (asset["id"],))
    filename = asset["name"].replace('"', "")
    return Response("", 200, {
        "X-Accel-Redirect": f"/_releases/{int(repo['id'])}/{int(asset['id'])}",
        "Content-Type": "application/octet-stream",
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-cache",
    })


def _not_found():
    return Response("Not Found\n", 404, mimetype="text/plain")


@bp.route("/<owner>/<name>/releases/download/<path:rest>", methods=["GET", "HEAD"])
def download(owner, name, rest):
    found, err = load_repo(owner, name)
    if err:
        return _not_found()
    repo, level = found
    tag, _, asset_name = rest.rpartition("/")
    if not tag:
        return _not_found()
    release = _release(repo, level, tag=tag)
    if release is None:
        return _not_found()
    a = db.query("SELECT * FROM release_assets WHERE release_id = %s AND name = %s", (release["id"], asset_name),
                 one=True)
    return send_asset(repo, a) if a else _not_found()


@bp.route("/<owner>/<name>/releases/latest/download/<asset_name>", methods=["GET", "HEAD"])
def download_latest(owner, name, asset_name):
    found, err = load_repo(owner, name)
    if err:
        return _not_found()
    repo, level = found
    release = pick_latest(visible_releases(repo, level))
    if release is None:
        return _not_found()
    a = db.query("SELECT * FROM release_assets WHERE release_id = %s AND name = %s", (release["id"], asset_name),
                 one=True)
    return send_asset(repo, a) if a else _not_found()


def delete_all(repo_id):
    shutil.rmtree(releases_dir(repo_id), ignore_errors=True)
