"""git over SSH: keys from the website, the forced command, and refusals."""

import os
import subprocess

import pytest

SSH_HOST = os.environ.get("MYGIT_SSH_HOST", "localhost")
SSH_PORT = os.environ.get("MYGIT_SSH_PORT", "2222")


def ssh_url(full_name, suffix=".git"):
    return f"ssh://git@{SSH_HOST}:{SSH_PORT}/{full_name}{suffix}"


class Keyed:
    """A key pair registered for a user, and git/ssh runners that use it."""

    def __init__(self, git, user, name="id"):
        self.git = git
        self.path = os.path.join(git.root, name)
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", self.path, "-C", name], check=True)
        r = user["api"].post("/api/user/keys", json={"key": open(self.path + ".pub").read(), "title": name})
        assert r.status_code == 201, r.text
        self.key = r.json()
        self.user = user
        self.ssh_opts = ["-i", self.path, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                         "-o", "StrictHostKeyChecking=accept-new",
                         "-o", f"UserKnownHostsFile={os.path.join(git.root, 'known_hosts')}"]
        self.env = {"GIT_SSH_COMMAND": "ssh " + " ".join(self.ssh_opts)}

    def run(self, *args, **kw):
        return self.git.run(*args, extra_env=self.env, **kw)

    def ssh(self, *remote):
        return subprocess.run(["ssh", *self.ssh_opts, "-p", SSH_PORT, f"git@{SSH_HOST}", *remote],
                              capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize("version", ["0", "2"])
def test_push_clone_pull_over_ssh(world, git, version):
    owner = world.user()
    k = Keyed(git, owner)
    repo = world.repo(owner)
    src = git.new_repo("src")
    k.run("-c", f"protocol.version={version}", "push", ssh_url(repo["full_name"]), "main", cwd=src)
    k.run("-c", f"protocol.version={version}", "clone", "-q", ssh_url(repo["full_name"], suffix=""), "copy")
    copy = os.path.join(git.root, "copy")
    sha = git.commit(src, "README.md", "v2\n")
    k.run("push", ssh_url(repo["full_name"]), "main", cwd=src)
    k.run("pull", "-q", "--ff-only", cwd=copy)
    assert git.run("rev-parse", "HEAD", cwd=copy).stdout.strip() == sha
    events = [e for e in owner["api"].get("/api/activity").json() if e["repo"] == repo["full_name"]]
    assert events[0]["via"] == "ssh" and events[0]["actor"] == owner["username"]
    assert owner["api"].get("/api/user/keys").json()[0]["last_used_at"] is not None


def test_archive_over_ssh(world, git):
    owner = world.user()
    k = Keyed(git, owner)
    repo = world.repo(owner)
    k.run("push", ssh_url(repo["full_name"]), "main", cwd=git.new_repo(files={"a/b.txt": "x\n"}))
    out = k.run("archive", f"--remote={ssh_url(repo['full_name'])}", "--format=tar", "main", "a/b.txt",
                cwd=git.root)
    assert "a/b.txt" in out.stdout


def test_greeting_and_no_shell(world, git):
    owner = world.user()
    k = Keyed(git, owner)
    greet = k.ssh()
    assert greet.returncode == 1
    assert f"Hi {owner['username']}! You've authenticated" in greet.stderr
    shell = k.ssh("id")
    assert shell.returncode == 1 and "only runs git commands" in shell.stderr
    sneaky = k.ssh("git-upload-pack '../../../etc'")
    assert sneaky.returncode == 1 and "only runs git commands" in sneaky.stderr


def test_ssh_refusals(world, git):
    owner, stranger = world.user(), world.user()
    repo = world.repo(owner, private=True)
    mine = Keyed(git, owner, "owner")
    mine.run("push", ssh_url(repo["full_name"]), "main", cwd=git.new_repo())
    theirs = Keyed(git, stranger, "stranger")
    out = theirs.run("ls-remote", ssh_url(repo["full_name"]), check=False)
    assert "ERROR: Repository not found." in out.stderr
    public = world.repo(owner)
    out = theirs.run("push", ssh_url(public["full_name"]), "main", cwd=os.path.join(git.root, "work"), check=False)
    assert f"Write access to {public['full_name']} denied" in out.stderr


def test_unknown_and_removed_keys(world, git, admin):
    owner = world.user()
    k = Keyed(git, owner)
    repo = world.repo(owner)
    k.run("ls-remote", ssh_url(repo["full_name"]))
    admin.patch(f"/api/admin/users/{owner['id']}", json={"is_active": False})
    assert "Permission denied (publickey)" in k.run("ls-remote", ssh_url(repo["full_name"]), check=False).stderr
    admin.patch(f"/api/admin/users/{owner['id']}", json={"is_active": True})
    owner["api"].delete(f"/api/user/keys/{k.key['id']}")
    assert "Permission denied (publickey)" in k.run("ls-remote", ssh_url(repo["full_name"]), check=False).stderr


def test_same_key_cannot_be_added_twice(world, git):
    a, b = world.user(), world.user()
    k = Keyed(git, a)
    r = b["api"].post("/api/user/keys", json={"key": open(k.path + ".pub").read()})
    assert r.status_code == 409


def test_bad_keys_are_rejected_with_reasons(world):
    user = world.user()
    cases = {
        "ssh-dss AAAAB3NzaC1kc3M=": "DSA",
        "-----BEGIN OPENSSH PRIVATE KEY-----\nxx\n-----END OPENSSH PRIVATE KEY-----": "private key",
        "hello": "looks like",
    }
    for text, needle in cases.items():
        r = user["api"].post("/api/user/keys", json={"key": text})
        assert r.status_code == 400 and needle in r.json()["error"], (text, r.text)
