"""Fixtures for the black-box suite: an admin API session, throwaway users,
tokens and repositories (all deleted afterwards), and a git runner."""

import os
import shutil
import subprocess
import tempfile
import uuid

import pytest
import requests

BASE = os.environ.get("MYGIT_BASE", "http://localhost:5564").rstrip("/")
HOST = BASE.split("://", 1)[1]
ADMIN = (os.environ.get("ADMIN_USERNAME", "admin"), os.environ["ADMIN_INITIAL_PASSWORD"])


class Api(requests.Session):
    def __init__(self):
        super().__init__()
        self.headers["X-Requested-With"] = "mygit"

    def request(self, method, url, **kw):
        if url.startswith("/"):
            url = BASE + url
        kw.setdefault("timeout", 60)
        return super().request(method, url, **kw)


def login(username, password):
    s = Api()
    r = s.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="session")
def admin():
    return login(*ADMIN)


def unique(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class World:
    """Creates users/repos/tokens on demand and removes them at teardown."""

    def __init__(self, admin_api):
        self.admin = admin_api
        self.users = []
        self.repos = []

    def user(self, is_admin=False):
        name = unique("qa")
        password = "qa-password-1"
        r = self.admin.post("/api/admin/users", json={"username": name, "password": password, "is_admin": is_admin})
        assert r.status_code == 201, r.text
        info = r.json()
        info["password"] = password
        info["api"] = login(name, password)
        self.users.append(info)
        return info

    def token(self, user, access="write"):
        r = user["api"].post("/api/user/tokens", json={"name": unique("t"), "access": access})
        assert r.status_code == 201, r.text
        return r.json()["token"]

    def repo(self, user, private=False, **extra):
        name = unique("repo")
        r = user["api"].post("/api/repos", json={"name": name, "private": private, **extra})
        assert r.status_code == 201, r.text
        repo = r.json()
        self.repos.append((user, repo))
        return repo

    def cleanup(self):
        for user, repo in reversed(self.repos):
            self.admin.delete(f"/api/repos/{repo['full_name']}")
        for user in self.users:
            self.admin.delete(f"/api/admin/users/{user['id']}")


@pytest.fixture
def world(admin):
    w = World(admin)
    yield w
    w.cleanup()


def http_url(repo_full_name, token=None, user="x", suffix=".git"):
    scheme, host = BASE.split("://", 1)
    cred = f"{user}:{token}@" if token else ""
    return f"{scheme}://{cred}{host}/{repo_full_name}{suffix}"


class Git:
    """Runs the git client in a scratch directory with no stored credentials."""

    def __init__(self, root):
        self.root = root
        self.home = os.path.join(root, "home")
        os.makedirs(self.home)
        self.env = {
            "PATH": os.environ["PATH"],
            "HOME": self.home,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "QA", "GIT_AUTHOR_EMAIL": "qa@example.com",
            "GIT_COMMITTER_NAME": "QA", "GIT_COMMITTER_EMAIL": "qa@example.com",
            "LANG": "C.UTF-8",
        }
        self.run("config", "--global", "init.defaultBranch", "main")
        self.run("config", "--global", "credential.helper", "")
        self.run("config", "--global", "advice.detachedHead", "false")

    def run(self, *args, cwd=None, check=True, extra_env=None, input=None):
        proc = subprocess.run(["git", *args], cwd=cwd or self.root, env={**self.env, **(extra_env or {})},
                              capture_output=True, text=True, input=input, timeout=900)
        if check and proc.returncode != 0:
            raise AssertionError(f"git {' '.join(args)} failed ({proc.returncode}):\n{proc.stdout}\n{proc.stderr}")
        return proc

    def new_repo(self, name="work", files=None):
        path = os.path.join(self.root, name)
        self.run("init", "-q", path)
        for rel, content in (files or {"README.md": "hello\n"}).items():
            full = os.path.join(path, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            mode = "wb" if isinstance(content, bytes) else "w"
            with open(full, mode) as f:
                f.write(content)
        self.run("add", "-A", cwd=path)
        self.run("commit", "-qm", "initial", cwd=path)
        return path

    def commit(self, path, rel, content, message="change"):
        with open(os.path.join(path, rel), "w") as f:
            f.write(content)
        self.run("add", "-A", cwd=path)
        self.run("commit", "-qm", message, cwd=path)
        return self.run("rev-parse", "HEAD", cwd=path).stdout.strip()


@pytest.fixture
def git():
    root = tempfile.mkdtemp(prefix="mygit-qa-")
    yield Git(root)
    shutil.rmtree(root, ignore_errors=True)
