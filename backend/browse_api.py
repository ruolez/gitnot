"""Read-only views of a repository's contents for the web pages."""

import json
import re
import subprocess

from flask import Blueprint, jsonify, request

import db
import gitcmd
from gitparse import LOG_FORMAT, parse_diff, parse_log, parse_ls_tree
from highlight import highlight_lines
from markdown_render import render_markdown
from refs import clean_path, split_ref_path
from repos_api import load_repo
from util import api_error

bp = Blueprint("browse", __name__, url_prefix="/api/repos/<owner>/<name>")

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
MAX_BLOB_VIEW = 1024 * 1024
README_NAMES = ("readme.md", "readme.markdown", "readme", "readme.txt", "readme.rst")
_SAFE_REF = re.compile(r"^(?!-)(?!.*\.\.)(?!.*@\{)[^\s~^:?*\[\\\x00-\x1f]+$")
PAGE_SIZE = 30


def is_binary(data):
    return b"\0" in data[:8000]


def ref_names(repo_id):
    out = gitcmd.text(repo_id, ["for-each-ref", "--format=%(refname)", "refs/heads/", "refs/tags/"])
    branches, tags = [], []
    for line in out.splitlines():
        if line.startswith("refs/heads/"):
            branches.append(line[len("refs/heads/"):])
        elif line.startswith("refs/tags/"):
            tags.append(line[len("refs/tags/"):])
    return branches, tags


def resolve_commit(repo_id, ref):
    """Full commit sha for a branch, tag or sha, or None."""
    if not ref or not _SAFE_REF.match(ref):
        return None
    for candidate in (f"refs/heads/{ref}", f"refs/tags/{ref}", ref):
        out = gitcmd.run(repo_id, ["rev-parse", "--verify", "--quiet", "--end-of-options", f"{candidate}^{{commit}}"],
                         check=False)
        sha = out.decode().strip()
        if len(sha) == 40:
            return sha
    return None


def object_at(repo_id, commit, path):
    """(type, sha, size) of `path` at `commit`, or None. path '' = root tree."""
    if not path:
        return ("tree", gitcmd.text(repo_id, ["rev-parse", f"{commit}^{{tree}}"]).strip(), None)
    out = gitcmd.run(repo_id, ["cat-file", "--batch-check=%(objecttype) %(objectname) %(objectsize)"],
                     input=f"{commit}:{path}\n".encode(), check=False).decode().strip()
    parts = out.split()
    if len(parts) != 3 or parts[1] == "missing":
        return None
    return parts[0], parts[1], int(parts[2])


def _context():
    """(repo, level, commit, ref, path) from ?ref=&path=, or an error response."""
    found, err = load_repo(request.view_args["owner"], request.view_args["name"])
    if err:
        return None, err
    repo, level = found
    ref = request.args.get("ref") or repo["default_branch"]
    path = clean_path(request.args.get("path", ""))
    if path is None:
        return None, api_error("Bad path")
    commit = resolve_commit(repo["id"], ref)
    if commit is None:
        return None, api_error(f"No branch, tag or commit named {ref}", 404)
    return (repo, level, commit, ref, path), None


def commit_json(c):
    return {**c, "short": c["sha"][:7]}


def log(repo_id, commit, path="", limit=PAGE_SIZE, skip=0, extra=None):
    args = ["-c", "core.quotePath=false", "log", f"--format={LOG_FORMAT}", f"--max-count={limit}",
            f"--skip={skip}", commit, *(extra or []), "--"]
    if path:
        args.append(path)
    return [commit_json(c) for c in parse_log(gitcmd.text(repo_id, args))]


@bp.get("/resolve")
def resolve(owner, name):
    """Split a URL tail (feature/login/src/app.py) into ref + path."""
    found, err = load_repo(owner, name)
    if err:
        return err
    repo, _level = found
    segments = [s for s in request.args.get("path", "").split("/") if s]
    if not segments:
        return jsonify({"ref": repo["default_branch"], "kind": "branch", "path": ""})
    branches, tags = ref_names(repo["id"])
    split = split_ref_path(segments, branches, tags)
    if split is None:
        return api_error("No such branch, tag or commit", 404)
    ref, kind, path = split
    if kind == "commit":
        sha = resolve_commit(repo["id"], ref)
        if sha is None:
            return api_error("No such commit", 404)
    return jsonify({"ref": ref, "kind": kind, "path": path})


@bp.get("/refs")
def list_refs(owner, name):
    found, err = load_repo(owner, name)
    if err:
        return err
    repo, _level = found
    fmt = "%(refname)%1f%(objectname)%1f%(*objectname)%1f%(creatordate:iso-strict)%1f%(subject)%1f%(objecttype)"
    out = gitcmd.text(repo["id"], ["for-each-ref", "--sort=-creatordate", f"--format={fmt}", "refs/heads/",
                                   "refs/tags/"])
    branches, tags = [], []
    for line in out.splitlines():
        name, sha, peeled, date, subject, kind = (line.split("\x1f") + [""] * 6)[:6]
        item = {"sha": peeled or sha, "date": date, "subject": subject}
        if name.startswith("refs/heads/"):
            branches.append({"name": name[len("refs/heads/"):], **item,
                             "default": name == f"refs/heads/{repo['default_branch']}"})
        elif name.startswith("refs/tags/"):
            tags.append({"name": name[len("refs/tags/"):], **item, "annotated": kind == "tag"})
    branches.sort(key=lambda b: (not b["default"],))
    return jsonify({"default_branch": repo["default_branch"], "branches": branches, "tags": tags})


def _readme(repo, commit, ref, path, entries):
    for wanted in README_NAMES:
        for e in entries:
            if e["type"] == "blob" and e["name"].lower() == wanted and (e["size"] or 0) <= MAX_BLOB_VIEW:
                text = gitcmd.run(repo["id"], ["cat-file", "blob", e["sha"]]).decode("utf-8", "replace")
                if wanted.endswith((".md", ".markdown")):
                    html = render_markdown(text, repo["owner"], repo["name"], ref, e["path"])
                    return {"name": e["name"], "path": e["path"], "html": html}
                return {"name": e["name"], "path": e["path"], "text": text}
    return None


@bp.get("/tree")
def tree(owner, name):
    ctx, err = _context()
    if err:
        return err
    repo, _level, commit, ref, path = ctx
    obj = object_at(repo["id"], commit, path)
    if obj is None:
        return api_error(f"{path} does not exist at {ref}", 404)
    if obj[0] != "tree":
        return jsonify({"kind": "blob", "path": path})
    spec = f"{commit}:{path}" if path else commit
    raw = gitcmd.run(repo["id"], ["ls-tree", "-z", "--long", spec])
    entries = parse_ls_tree(raw)
    for e in entries:
        e["path"] = f"{path}/{e['name']}" if path else e["name"]
    last = log(repo["id"], commit, path, limit=1)
    count = gitcmd.text(repo["id"], ["rev-list", "--count", commit, "--", *([path] if path else [])]).strip()
    return jsonify({
        "kind": "tree",
        "ref": ref,
        "commit": commit,
        "path": path,
        "entries": entries,
        "last_commit": last[0] if last else None,
        "commit_count": int(count or 0),
        "readme": _readme(repo, commit, ref, path, entries),
    })


@bp.get("/tree-commits")
def tree_commits(owner, name):
    """Last commit touching each entry of a directory (filled in after the page shows)."""
    ctx, err = _context()
    if err:
        return err
    repo, _level, commit, _ref, path = ctx
    cached = db.query("SELECT data FROM tree_commit_cache WHERE repo_id = %s AND commit_sha = %s AND path = %s",
                      (repo["id"], commit, path), one=True)
    if cached:
        return jsonify(cached["data"])
    spec = f"{commit}:{path}" if path else commit
    names = {e["name"] for e in parse_ls_tree(gitcmd.run(repo["id"], ["ls-tree", "-z", spec]))}
    result = last_commits(repo["id"], commit, path, names)
    db.execute(
        """INSERT INTO tree_commit_cache (repo_id, commit_sha, path, data) VALUES (%s, %s, %s, %s)
           ON CONFLICT DO NOTHING""",
        (repo["id"], commit, path, json.dumps(result)),
    )
    return jsonify(result)


def last_commits(repo_id, commit, path, names, max_commits=5000):
    """{entry name: {sha, subject, date, author}} by walking history once."""
    found = {}
    prefix = f"{path}/" if path else ""
    cmd = ["git", "--git-dir", gitcmd.repo_path(repo_id), "-c", "core.quotePath=false", "log",
           "--format=%x1e%H%x1f%cI%x1f%an%x1f%s", "--name-only", "--no-renames", f"--max-count={max_commits}",
           commit, "--"]
    if path:
        cmd.append(path)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=gitcmd._ENV)
    current = None
    try:
        for raw in proc.stdout:
            line = raw.decode("utf-8", "replace").rstrip("\n")
            if line.startswith("\x1e"):
                sha, date, author, subject = (line[1:].split("\x1f") + [""] * 4)[:4]
                current = {"sha": sha, "date": date, "author": author, "subject": subject}
                continue
            if not line or current is None or not line.startswith(prefix):
                continue
            name = line[len(prefix):].split("/", 1)[0]
            if name in names and name not in found:
                found[name] = current
                if len(found) == len(names):
                    break
    finally:
        proc.kill()
        proc.wait()
    return found


@bp.get("/blob")
def blob(owner, name):
    ctx, err = _context()
    if err:
        return err
    repo, _level, commit, ref, path = ctx
    obj = object_at(repo["id"], commit, path)
    if obj is None:
        return api_error(f"{path} does not exist at {ref}", 404)
    kind, sha, size = obj
    if kind == "tree":
        return jsonify({"kind": "tree", "path": path})
    last = log(repo["id"], commit, path, limit=1)
    out = {"kind": "blob", "ref": ref, "commit": commit, "path": path, "sha": sha, "size": size,
           "last_commit": last[0] if last else None, "binary": False, "too_large": False}
    mode = gitcmd.text(repo["id"], ["ls-tree", commit, "--", path]).split(" ", 1)[0]
    if mode == "120000":
        out["symlink_target"] = gitcmd.run(repo["id"], ["cat-file", "blob", sha]).decode("utf-8", "replace")
        return jsonify(out)
    if size > MAX_BLOB_VIEW:
        out["too_large"] = True
        return jsonify(out)
    data = gitcmd.run(repo["id"], ["cat-file", "blob", sha])
    if is_binary(data):
        out["binary"] = True
        return jsonify(out)
    text = data.decode("utf-8", "replace")
    language, lines = highlight_lines(text, path)
    out.update(language=language, lines=lines, line_count=len(lines))
    if path.lower().endswith((".md", ".markdown")):
        out["markdown_html"] = render_markdown(text, repo["owner"], repo["name"], ref, path)
    return jsonify(out)


@bp.get("/commits")
def commits(owner, name):
    ctx, err = _context()
    if err:
        return err
    repo, _level, commit, ref, path = ctx
    page = max(1, min(int(request.args.get("page", 1) or 1), 10000))
    items = log(repo["id"], commit, path, limit=PAGE_SIZE + 1, skip=(page - 1) * PAGE_SIZE)
    return jsonify({"ref": ref, "path": path, "page": page, "commits": items[:PAGE_SIZE],
                    "has_more": len(items) > PAGE_SIZE})


def diff_between(repo_id, base, head):
    text = gitcmd.text(repo_id, ["-c", "core.quotePath=false", "diff", "--no-color", "--no-ext-diff", "-M",
                                 "--full-index", "-U3", base, head], max_bytes=30 * 1024 * 1024, timeout=60)
    return parse_diff(text)


@bp.get("/commit/<sha>")
def commit_detail(owner, name, sha):
    found, err = load_repo(owner, name)
    if err:
        return err
    repo, _level = found
    full = resolve_commit(repo["id"], sha)
    if full is None:
        return api_error("No such commit", 404)
    info = log(repo["id"], full, limit=1)[0]
    base = info["parents"][0] if info["parents"] else EMPTY_TREE
    branches = gitcmd.text(repo["id"], ["for-each-ref", "--contains", full, "--format=%(refname:strip=2)",
                                        "refs/heads/"]).split()
    return jsonify({"commit": info, "diff": diff_between(repo["id"], base, full), "branches": branches[:20]})


@bp.get("/compare/<path:spec>")
def compare(owner, name, spec):
    found, err = load_repo(owner, name)
    if err:
        return err
    repo, _level = found
    if "..." in spec:
        base_ref, head_ref = spec.split("...", 1)
    elif ".." in spec:
        base_ref, head_ref = spec.split("..", 1)
    else:
        base_ref, head_ref = repo["default_branch"], spec
    base, head = resolve_commit(repo["id"], base_ref), resolve_commit(repo["id"], head_ref)
    if base is None or head is None:
        return api_error("Unknown branch, tag or commit", 404)
    merge_base = gitcmd.run(repo["id"], ["merge-base", base, head], check=False).decode().strip() or base
    commits_ = log(repo["id"], head, limit=250, extra=["--not", merge_base])
    return jsonify({"base": base_ref, "head": head_ref, "base_sha": base, "head_sha": head,
                    "merge_base": merge_base, "commits": commits_, "diff": diff_between(repo["id"], merge_base, head)})
