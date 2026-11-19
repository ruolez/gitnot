"""Parsers for git plumbing output. Pure functions; gitcmd runs the commands."""

import re

LOG_FORMAT = "%H%x1f%P%x1f%an%x1f%ae%x1f%aI%x1f%cn%x1f%ce%x1f%cI%x1f%s%x1f%b%x1e"
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")


def parse_ls_tree(raw):
    """Entries from `git ls-tree -z [--long]`: directories first, then by name."""
    entries = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        meta, _, path = item.partition(b"\t")
        fields = meta.decode().split()
        mode, kind, sha = fields[:3]
        size = fields[3] if len(fields) > 3 else "-"
        name = path.decode("utf-8", "replace")
        if kind == "blob" and mode == "120000":
            kind = "symlink"
        elif kind == "commit":
            kind = "submodule"
        entries.append({
            "name": name.rsplit("/", 1)[-1],
            "path": name,
            "type": kind,
            "mode": mode,
            "sha": sha,
            "size": int(size) if size.strip().isdigit() else None,
        })
    order = {"tree": 0, "submodule": 1, "symlink": 2, "blob": 2}
    entries.sort(key=lambda e: (order.get(e["type"], 3), e["name"].lower()))
    return entries


def parse_log(raw):
    commits = []
    for record in raw.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        f = record.split("\x1f")
        if len(f) < 10:
            continue
        commits.append({
            "sha": f[0],
            "parents": f[1].split() if f[1] else [],
            "author": {"name": f[2], "email": f[3], "date": f[4]},
            "committer": {"name": f[5], "email": f[6], "date": f[7]},
            "subject": f[8],
            "body": f[9].strip(),
        })
    return commits


def _strip_prefix(path, prefix):
    if path == "/dev/null":
        return None
    if path.startswith('"') and path.endswith('"'):
        path = path[1:-1].encode("latin-1", "backslashreplace").decode("unicode_escape").encode("latin-1").decode(
            "utf-8", "replace")
    return path[2:] if path.startswith(prefix) else path


def parse_diff(text, max_files=300, max_lines=20000, max_file_lines=3000):
    """Files from a unified diff (`git diff --no-color -M`). Each file has
    path, old_path, status (added/deleted/renamed/modified/copied), binary,
    additions, deletions and hunks of lines {t, old, new, text}. Large diffs
    are cut: `truncated` on a file or on the whole result."""
    files = []
    total_lines = 0
    truncated = False
    cur = None
    hunk = None
    old_no = new_no = 0

    def finish():
        nonlocal cur
        if cur is not None:
            if cur["path"] is None:
                cur["path"] = cur["old_path"]
            files.append(cur)
        cur = None

    for line in text.split("\n"):
        if line.startswith("diff --git "):
            finish()
            hunk = None
            if len(files) >= max_files:
                truncated = True
                break
            rest = line[len("diff --git "):]
            a, b = rest, rest
            half = len(rest) // 2
            if rest[:half].startswith("a/") and rest[half + 1:].startswith("b/") and rest[2:half] == rest[half + 3:]:
                a, b = rest[:half], rest[half + 1:]
            cur = {"path": _strip_prefix(b, "b/"), "old_path": _strip_prefix(a, "a/"), "status": "modified",
                   "binary": False, "additions": 0, "deletions": 0, "hunks": [], "truncated": False,
                   "_lines": 0}
            continue
        if cur is None:
            continue
        if hunk is None or not line or line[0] not in " +-\\":
            if line.startswith("new file mode"):
                cur["status"] = "added"
            elif line.startswith("deleted file mode"):
                cur["status"] = "deleted"
            elif line.startswith("rename from "):
                cur["status"], cur["old_path"] = "renamed", line[len("rename from "):]
            elif line.startswith("rename to "):
                cur["path"] = line[len("rename to "):]
            elif line.startswith("copy from "):
                cur["status"], cur["old_path"] = "copied", line[len("copy from "):]
            elif line.startswith("copy to "):
                cur["path"] = line[len("copy to "):]
            elif line.startswith("Binary files ") or line == "GIT binary patch":
                cur["binary"] = True
            elif line.startswith("--- "):
                old = _strip_prefix(line[4:].split("\t")[0], "a/")
                if old is None:
                    cur["status"] = "added"
                else:
                    cur["old_path"] = old
            elif line.startswith("+++ "):
                new = _strip_prefix(line[4:].split("\t")[0], "b/")
                if new is None:
                    cur["status"] = "deleted"
                    cur["path"] = cur["old_path"]
                else:
                    cur["path"] = new
            m = _HUNK.match(line)
            if m:
                old_no, new_no = int(m.group(1)), int(m.group(3))
                hunk = {"header": line, "lines": []}
                if cur["_lines"] < max_file_lines and total_lines < max_lines:
                    cur["hunks"].append(hunk)
                else:
                    cur["truncated"] = True
            continue
        m = _HUNK.match(line)
        if m:
            old_no, new_no = int(m.group(1)), int(m.group(3))
            hunk = {"header": line, "lines": []}
            if cur["_lines"] < max_file_lines and total_lines < max_lines:
                cur["hunks"].append(hunk)
            else:
                cur["truncated"] = True
            continue
        kind = line[0]
        if kind == "\\":
            continue
        entry = {"t": kind, "text": line[1:]}
        if kind == "+":
            cur["additions"] += 1
            entry["new"] = new_no
            new_no += 1
        elif kind == "-":
            cur["deletions"] += 1
            entry["old"] = old_no
            old_no += 1
        else:
            entry["old"], entry["new"] = old_no, new_no
            old_no += 1
            new_no += 1
        if cur["_lines"] < max_file_lines and total_lines < max_lines:
            hunk["lines"].append(entry)
            cur["_lines"] += 1
            total_lines += 1
        else:
            cur["truncated"] = True
    finish()
    for f in files:
        f.pop("_lines", None)
        if f["status"] not in ("renamed", "copied"):
            f["old_path"] = None
    if total_lines >= max_lines:
        truncated = True
    return {"files": files, "truncated": truncated,
            "additions": sum(f["additions"] for f in files), "deletions": sum(f["deletions"] for f in files)}
