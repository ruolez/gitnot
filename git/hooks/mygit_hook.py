"""Shared code for the pre-receive and post-receive hooks."""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

ZERO = "0" * 40


def repo_id():
    # git runs hooks inside the bare repository: /data/repos/<id>.git
    name = os.path.basename(os.path.abspath(os.environ.get("GIT_DIR", ".")))
    return int(name[: -len(".git")]) if name.endswith(".git") and name[:-4].isdigit() else 0


def read_updates():
    updates = []
    for line in sys.stdin.read().splitlines():
        parts = line.split()
        if len(parts) == 3:
            updates.append({"old": parts[0], "new": parts[1], "ref": parts[2]})
    return updates


def context():
    return {
        "repo_id": repo_id(),
        "user_id": os.environ.get("MYGIT_USER_ID") or None,
        "actor": os.environ.get("MYGIT_USER") or os.environ.get("REMOTE_USER") or "",
        "via": os.environ.get("MYGIT_VIA") or "http",
    }


def call(path, payload, timeout=30):
    with open("/etc/mygit/internal-token") as f:
        token = f.read().strip()
    with open("/etc/mygit/backend-url") as f:
        base = f.read().strip()
    req = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-Internal-Token": token},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read() or b"{}")


def git(*args, input=None):
    return subprocess.run(["git", *args], input=input, capture_output=True)


def say(lines):
    for line in lines:
        print(line, flush=True)
