"""Files and archives at GitHub-style URLs, for browsers, curl and installers:

  /<owner>/<repo>/raw/<ref>/<path>
  /raw/<owner>/<repo>/<ref>/<path>               (raw.githubusercontent.com layout)
  /raw/<owner>/<repo>/refs/heads/<branch>/<path>
  /<owner>/<repo>/archive/<ref>.tar.gz | .zip
  /<owner>/<repo>/archive/refs/heads/<branch>.tar.gz

Content is never rendered as a page on this origin: text is text/plain and
every response carries a sandbox CSP, so a pushed .html or .svg can't run
script with a visitor's session."""

import mimetypes
import re
import subprocess

from flask import Blueprint, Response, request

import gitcmd
from browse_api import is_binary, object_at, ref_names, resolve_commit
from refs import clean_path, split_ref_path
from repos_api import load_repo

bp = Blueprint("raw", __name__)

SAFE_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
    ".webp": "image/webp", ".ico": "image/x-icon", ".bmp": "image/bmp", ".avif": "image/avif",
    ".svg": "image/svg+xml", ".pdf": "application/pdf", ".mp4": "video/mp4", ".webm": "video/webm",
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".woff": "font/woff", ".woff2": "font/woff2",
}
SANDBOX_CSP = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; media-src 'self'; sandbox"
ARCHIVE_FORMATS = {".tar.gz": ("tar.gz", "application/gzip"), ".tgz": ("tar.gz", "application/gzip"),
                   ".zip": ("zip", "application/zip"), ".tar": ("tar", "application/x-tar")}
CHUNK = 64 * 1024


def _not_found(message="404: Not Found"):
    return Response(message + "\n", 404, mimetype="text/plain", headers={"Content-Security-Policy": SANDBOX_CSP})


def content_type_for(path, head):
    ext = ("." + path.rsplit(".", 1)[-1].lower()) if "." in path.rsplit("/", 1)[-1] else ""
    if ext in SAFE_TYPES:
        return SAFE_TYPES[ext]
    if not is_binary(head):
        return "text/plain; charset=utf-8"
    return "application/octet-stream"


def _start(cmd):
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=gitcmd._ENV)


def _stream(proc, first=b""):
    def gen():
        try:
            if first:
                yield first
            while True:
                chunk = proc.stdout.read(CHUNK)
                if not chunk:
                    break
                yield chunk
        finally:
            proc.kill()
            proc.wait()

    return gen()


def serve_raw(owner, name, rest):
    found, err = load_repo(owner, name)
    if err:
        return _not_found()
    repo, _level = found
    segments = [s for s in rest.split("/") if s]
    branches, tags = ref_names(repo["id"])
    split = split_ref_path(segments, branches, tags)
    if split is None:
        return _not_found()
    ref, _kind, path = split
    path = clean_path(path)
    commit = resolve_commit(repo["id"], ref)
    if not path or commit is None:
        return _not_found()
    obj = object_at(repo["id"], commit, path)
    if obj is None or obj[0] != "blob":
        return _not_found()
    _type, sha, size = obj
    etag = f'"{sha}"'
    headers = {
        "ETag": etag,
        "Cache-Control": "no-cache",
        "Content-Security-Policy": SANDBOX_CSP,
        "X-Content-Type-Options": "nosniff",
        "Access-Control-Allow-Origin": "*",
        "Content-Disposition": f"inline; filename=\"{path.rsplit('/', 1)[-1].replace(chr(34), '')}\"",
    }
    if etag in (request.headers.get("If-None-Match") or ""):
        return Response(status=304, headers=headers)
    proc = _start(["git", "--git-dir", gitcmd.repo_path(repo["id"]), "cat-file", "blob", sha])
    head = proc.stdout.read(min(size, 8000)) if size else b""
    headers["Content-Type"] = content_type_for(path, head)
    headers["Content-Length"] = str(size)
    if request.method == "HEAD":
        proc.kill()
        proc.wait()
        return Response(status=200, headers=headers)
    return Response(_stream(proc, head), status=200, headers=headers, direct_passthrough=True)


@bp.route("/<owner>/<name>/raw/<path:rest>", methods=["GET", "HEAD"])
def raw_in_repo(owner, name, rest):
    return serve_raw(owner, name, rest)


@bp.route("/raw/<owner>/<name>/<path:rest>", methods=["GET", "HEAD"])
def raw_top(owner, name, rest):
    return serve_raw(owner, name, rest)


def _archive_name(ref):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", ref).strip("-") or "archive"


@bp.route("/<owner>/<name>/archive/<path:rest>", methods=["GET", "HEAD"])
def archive(owner, name, rest):
    found, err = load_repo(owner, name)
    if err:
        return _not_found()
    repo, _level = found
    for suffix, (fmt, mime) in ARCHIVE_FORMATS.items():
        if rest.endswith(suffix):
            ref_part = rest[: -len(suffix)]
            break
    else:
        return _not_found()
    segments = [s for s in ref_part.split("/") if s]
    branches, tags = ref_names(repo["id"])
    split = split_ref_path(segments, branches, tags)
    if split is None or split[2]:
        return _not_found()
    ref = split[0]
    commit = resolve_commit(repo["id"], ref)
    if commit is None:
        return _not_found()
    prefix = f"{repo['name']}-{_archive_name(ref)}"
    headers = {
        "Content-Type": mime,
        "Content-Disposition": f'attachment; filename="{prefix}{suffix}"',
        "ETag": f'"{commit}-{fmt}"',
        "Cache-Control": "no-cache",
        "Content-Security-Policy": SANDBOX_CSP,
    }
    if request.method == "HEAD":
        return Response(status=200, headers=headers)
    proc = _start(["git", "--git-dir", gitcmd.repo_path(repo["id"]), "archive", f"--format={fmt}",
                   f"--prefix={prefix}/", commit])
    return Response(_stream(proc), status=200, headers=headers, direct_passthrough=True)
