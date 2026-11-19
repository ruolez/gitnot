"""Splitting URL paths like /tree/feature/login/src/app.py into a ref and a
path. Branch names may contain slashes, so the longest name that matches wins
(GitHub does the same)."""

import re

SHA_RE = re.compile(r"^[0-9a-f]{4,40}$")


def split_ref_path(segments, branches, tags):
    """(ref, kind, path) where kind is 'branch' | 'tag' | 'commit', or None.

    segments: URL path pieces after /tree/ (already decoded).
    branches, tags: names that exist. A leading `refs/heads/` or `refs/tags/`
    is accepted too (raw.githubusercontent-style URLs use it)."""
    if not segments:
        return None
    segs = list(segments)
    if len(segs) >= 3 and segs[0] == "refs" and segs[1] in ("heads", "tags"):
        pool = set(branches) if segs[1] == "heads" else set(tags)
        kind = "branch" if segs[1] == "heads" else "tag"
        for n in range(len(segs) - 2, 0, -1):
            name = "/".join(segs[2:2 + n])
            if name in pool:
                return name, kind, "/".join(segs[2 + n:])
        return None
    branch_set, tag_set = set(branches), set(tags)
    for n in range(len(segs), 0, -1):
        name = "/".join(segs[:n])
        if name in branch_set:
            return name, "branch", "/".join(segs[n:])
        if name in tag_set:
            return name, "tag", "/".join(segs[n:])
    if SHA_RE.match(segs[0]):
        return segs[0], "commit", "/".join(segs[1:])
    return None


def clean_path(path):
    """A repository-relative path without empty, '.' or '..' pieces, or None."""
    parts = [p for p in (path or "").split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts) or any(c in p for p in parts for c in "\0\n\r"):
        return None
    return "/".join(parts)
