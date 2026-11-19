"""git over HTTP(S) with a real git client: the commands people and the
installers use, both wire protocol versions, and every refusal path."""

import os
import threading

import pytest
from conftest import BASE, http_url

PROTOCOLS = ["0", "2"]


def proto(version):
    return ["-c", f"protocol.version={version}"]


@pytest.mark.parametrize("version", PROTOCOLS)
def test_push_clone_fetch_pull_roundtrip(world, git, version):
    owner = world.user()
    token = world.token(owner)
    repo = world.repo(owner)
    url = http_url(repo["full_name"], token)
    src = git.new_repo("src")
    git.run(*proto(version), "push", url, "main", cwd=src)

    git.run(*proto(version), "clone", "-q", http_url(repo["full_name"]), "copy")
    copy = os.path.join(git.root, "copy")
    assert open(os.path.join(copy, "README.md")).read() == "hello\n"

    second = git.commit(src, "README.md", "hello again\n")
    git.run(*proto(version), "push", url, "main", cwd=src)
    git.run(*proto(version), "pull", "-q", "--ff-only", cwd=copy)
    assert git.run("rev-parse", "HEAD", cwd=copy).stdout.strip() == second

    listed = git.run(*proto(version), "ls-remote", http_url(repo["full_name"])).stdout
    assert f"{second}\trefs/heads/main" in listed
    assert f"{second}\tHEAD" in listed


def test_clone_without_dot_git_suffix(world, git):
    owner = world.user()
    repo = world.repo(owner)
    git.run("push", http_url(repo["full_name"], world.token(owner)), "main", cwd=git.new_repo())
    git.run("clone", "-q", http_url(repo["full_name"], suffix=""), "plain")
    assert os.path.exists(os.path.join(git.root, "plain", "README.md"))


def test_empty_repository_clones_with_warning(world, git):
    owner = world.user()
    repo = world.repo(owner)
    out = git.run("clone", http_url(repo["full_name"]), "empty")
    assert "empty repository" in out.stderr


def test_branches_tags_and_force_push(world, git):
    owner = world.user()
    repo = world.repo(owner)
    url = http_url(repo["full_name"], world.token(owner))
    src = git.new_repo()
    git.run("push", url, "main", cwd=src)
    git.run("checkout", "-qb", "feature/x", cwd=src)
    git.commit(src, "a.txt", "a\n")
    git.run("tag", "-a", "v1.0.0", "-m", "first", cwd=src)
    git.run("push", "--follow-tags", url, "feature/x", cwd=src)
    refs = git.run("ls-remote", url).stdout
    assert "refs/heads/feature/x" in refs and "refs/tags/v1.0.0" in refs

    git.run("commit", "-q", "--amend", "-m", "rewritten", cwd=src)
    git.run("push", "--force", url, "feature/x", cwd=src)
    git.run("push", url, "--delete", "feature/x", cwd=src)
    git.run("push", url, "--delete", "v1.0.0", cwd=src)
    refs = git.run("ls-remote", url).stdout
    assert "feature/x" not in refs and "v1.0.0" not in refs


def test_default_branch_cannot_be_deleted(world, git):
    owner = world.user()
    repo = world.repo(owner)
    url = http_url(repo["full_name"], world.token(owner))
    src = git.new_repo()
    git.run("push", url, "main", cwd=src)
    out = git.run("push", url, "--delete", "main", cwd=src, check=False)
    assert out.returncode != 0
    assert "default branch can't be deleted" in out.stderr


def test_first_push_of_master_moves_head(world, git, admin):
    owner = world.user()
    repo = world.repo(owner)
    src = git.new_repo()
    git.run("branch", "-m", "master", cwd=src)
    git.run("push", http_url(repo["full_name"], world.token(owner)), "master", cwd=src)
    assert admin.get(f"/api/repos/{repo['full_name']}").json()["default_branch"] == "master"
    git.run("clone", "-q", http_url(repo["full_name"]), "c")
    assert git.run("branch", "--show-current", cwd=os.path.join(git.root, "c")).stdout.strip() == "master"


def test_shallow_and_partial_clones(world, git):
    owner = world.user()
    repo = world.repo(owner)
    src = git.new_repo()
    for i in range(3):
        git.commit(src, "n.txt", f"{i}\n")
    git.run("push", http_url(repo["full_name"], world.token(owner)), "main", cwd=src)

    git.run("clone", "-q", "--depth", "1", http_url(repo["full_name"]), "shallow")
    shallow = os.path.join(git.root, "shallow")
    assert git.run("rev-list", "--count", "HEAD", cwd=shallow).stdout.strip() == "1"

    git.run("clone", "-q", "--filter=blob:none", http_url(repo["full_name"]), "partial")
    partial = os.path.join(git.root, "partial")
    assert git.run("config", "remote.origin.promisor", cwd=partial).stdout.strip() == "true"
    assert open(os.path.join(partial, "n.txt")).read() == "2\n"


def test_large_push_and_clone(world, git):
    """~60 MB of incompressible data plus 3000 files: big enough that git
    streams the push chunked through nginx."""
    owner = world.user()
    repo = world.repo(owner)
    files = {f"many/f{i}.txt": f"{i}\n" for i in range(3000)}
    files["blob.bin"] = os.urandom(60 * 1024 * 1024)
    src = git.new_repo(files=files)
    git.run("push", http_url(repo["full_name"], world.token(owner)), "main", cwd=src)
    git.run("clone", "-q", http_url(repo["full_name"]), "big")
    assert os.path.getsize(os.path.join(git.root, "big", "blob.bin")) == 60 * 1024 * 1024


def test_file_size_limit(world, git, admin):
    owner = world.user()
    repo = world.repo(owner)
    before = admin.get("/api/admin/settings").json()["max_file_mb"]
    admin.patch("/api/admin/settings", json={"max_file_mb": 1})
    try:
        src = git.new_repo(files={"ok.txt": "fine\n", "assets/huge.bin": os.urandom(2 * 1024 * 1024)})
        out = git.run("push", http_url(repo["full_name"], world.token(owner)), "main", cwd=src, check=False)
        assert out.returncode != 0
        assert "assets/huge.bin (2.0 MB)" in out.stderr
        assert "refs/heads/main" not in git.run("ls-remote", http_url(repo["full_name"], world.token(owner))).stdout
    finally:
        admin.patch("/api/admin/settings", json={"max_file_mb": before})


def test_concurrent_pushes_to_different_branches(world, git):
    owner = world.user()
    repo = world.repo(owner)
    url = http_url(repo["full_name"], world.token(owner))
    src = git.new_repo()
    git.run("push", url, "main", cwd=src)
    results = {}

    def push(branch):
        path = os.path.join(git.root, branch)
        git.run("clone", "-q", url, path)
        git.run("checkout", "-qb", branch, cwd=path)
        git.commit(path, f"{branch}.txt", branch)
        results[branch] = git.run("push", "origin", branch, cwd=path, check=False).returncode

    threads = [threading.Thread(target=push, args=(f"b{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == {f"b{i}": 0 for i in range(4)}
    refs = git.run("ls-remote", url).stdout
    assert all(f"refs/heads/b{i}" in refs for i in range(4))


class TestRefusals:
    def test_anonymous_push_asks_for_credentials(self, world, git):
        owner = world.user()
        repo = world.repo(owner)
        out = git.run("push", http_url(repo["full_name"]), "main", cwd=git.new_repo(), check=False)
        assert "could not read Username" in out.stderr

    def test_anonymous_private_clone_asks_for_credentials(self, world, git):
        owner = world.user()
        repo = world.repo(owner, private=True)
        out = git.run("clone", http_url(repo["full_name"]), "x", check=False)
        assert "could not read Username" in out.stderr

    def test_private_repo_clones_with_owner_token(self, world, git):
        owner = world.user()
        repo = world.repo(owner, private=True)
        token = world.token(owner)
        git.run("push", http_url(repo["full_name"], token), "main", cwd=git.new_repo())
        git.run("clone", "-q", http_url(repo["full_name"], token), "p")

    def test_stranger_sees_private_repo_as_missing(self, world, git):
        owner, stranger = world.user(), world.user()
        repo = world.repo(owner, private=True)
        out = git.run("ls-remote", http_url(repo["full_name"], world.token(stranger)), check=False)
        assert "remote error: Repository not found" in out.stderr

    def test_missing_repo(self, world, git):
        user = world.user()
        out = git.run("ls-remote", http_url(f"{user['username']}/nope", world.token(user)), check=False)
        assert "remote error: Repository not found" in out.stderr

    def test_read_token_cannot_push(self, world, git):
        owner = world.user()
        repo = world.repo(owner)
        out = git.run("push", http_url(repo["full_name"], world.token(owner, "read")), "main",
                      cwd=git.new_repo(), check=False)
        assert f"Write access to {repo['full_name']} denied" in out.stderr

    def test_stranger_cannot_push_to_public_repo(self, world, git):
        owner, stranger = world.user(), world.user()
        repo = world.repo(owner)
        out = git.run("push", http_url(repo["full_name"], world.token(stranger)), "main",
                      cwd=git.new_repo(), check=False)
        assert "denied" in out.stderr

    def test_bad_token_is_rejected(self, world, git):
        owner = world.user()
        repo = world.repo(owner, private=True)
        bad = "mgp_" + "A" * 36
        out = git.run("ls-remote", http_url(repo["full_name"], bad), check=False)
        assert "Authentication failed" in out.stderr

    def test_account_password_is_not_a_git_credential(self, world, git):
        owner = world.user()
        repo = world.repo(owner, private=True)
        out = git.run("ls-remote", http_url(repo["full_name"], owner["password"], user=owner["username"]),
                      check=False)
        assert "Authentication failed" in out.stderr

    def test_revoked_token_and_deactivated_user(self, world, git, admin):
        owner = world.user()
        repo = world.repo(owner, private=True)
        token = world.token(owner)
        url = http_url(repo["full_name"], token)
        git.run("ls-remote", url)
        admin.patch(f"/api/admin/users/{owner['id']}", json={"is_active": False})
        assert "Authentication failed" in git.run("ls-remote", url, check=False).stderr
        admin.patch(f"/api/admin/users/{owner['id']}", json={"is_active": True})
        git.run("ls-remote", url)
        tokens = owner["api"].get("/api/user/tokens").json()
        for t in tokens:
            owner["api"].delete(f"/api/user/tokens/{t['id']}")
        assert "Authentication failed" in git.run("ls-remote", url, check=False).stderr


def test_push_history_is_recorded(world, git):
    owner = world.user()
    repo = world.repo(owner)
    git.run("push", http_url(repo["full_name"], world.token(owner)), "main", cwd=git.new_repo())
    events = owner["api"].get("/api/activity").json()
    mine = [e for e in events if e["repo"] == repo["full_name"]]
    assert mine and mine[0]["ref"] == "refs/heads/main" and mine[0]["actor"] == owner["username"]
    assert mine[0]["via"] == "http"
    assert owner["api"].get(f"/api/repos/{repo['full_name']}").json()["empty"] is False
