"""The one place the backend runs git. Argument lists only (no shell), a
timeout, and capped output."""

import os
import subprocess

import config

ZERO_SHA = "0" * 40
_ENV = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "HOME": "/tmp",
    "LANG": "C.UTF-8",
    "GIT_TERMINAL_PROMPT": "0",
    # The web pages never run hooks; pushes do that in the git container.
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "core.hooksPath",
    "GIT_CONFIG_VALUE_0": "/dev/null",
}


class GitError(Exception):
    def __init__(self, args, code, stderr):
        super().__init__(f"git {' '.join(args[:2])} failed ({code}): {stderr.strip()[:500]}")
        self.code = code
        self.stderr = stderr


def repo_path(repo_id):
    return os.path.join(config.REPOS_DIR, f"{int(repo_id)}.git")


def run(repo_id, args, *, input=None, timeout=30, max_bytes=50 * 1024 * 1024, check=True, env=None):
    """stdout of `git <args>` in repository `repo_id` (bytes)."""
    cmd = ["git", "--git-dir", repo_path(repo_id), *args] if repo_id is not None else ["git", *args]
    proc = subprocess.run(
        cmd, input=input, capture_output=True, timeout=timeout, env={**_ENV, **(env or {})}
    )
    if check and proc.returncode != 0:
        raise GitError(args, proc.returncode, proc.stderr.decode("utf-8", "replace"))
    if len(proc.stdout) > max_bytes:
        raise GitError(args, -1, "output too large")
    return proc.stdout


def text(repo_id, args, **kw):
    return run(repo_id, args, **kw).decode("utf-8", "replace")


def init_bare(repo_id, default_branch):
    path = repo_path(repo_id)
    run(None, ["init", "--quiet", "--bare", f"--initial-branch={default_branch}", path])
    # Tell `git clone` over dumb paths nothing; smart HTTP needs no export flag.
    for f in ("description", "hooks"):
        target = os.path.join(path, f)
        if os.path.isdir(target):
            for name in os.listdir(target):
                os.remove(os.path.join(target, name))
            os.rmdir(target)
        elif os.path.exists(target):
            os.remove(target)
    return path


def ref_exists(repo_id, ref):
    return subprocess.run(
        ["git", "--git-dir", repo_path(repo_id), "show-ref", "--verify", "--quiet", ref],
        env=_ENV, timeout=10,
    ).returncode == 0


def branches(repo_id):
    out = text(repo_id, ["for-each-ref", "--format=%(refname:strip=2)", "refs/heads/"])
    return [line for line in out.splitlines() if line]


def head_branch(repo_id):
    out = run(repo_id, ["symbolic-ref", "--quiet", "--short", "HEAD"], check=False)
    return out.decode().strip() or None


def set_head(repo_id, branch):
    run(repo_id, ["symbolic-ref", "HEAD", f"refs/heads/{branch}"])


def size_kb(repo_id):
    total = 0
    for root, _dirs, files in os.walk(repo_path(repo_id)):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total // 1024
