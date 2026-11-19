"""Collaborators, protected refs, deploy tokens, rename/transfer redirects,
archiving and visibility, all checked with real git commands."""

import os

import pytest
import requests
from conftest import BASE, http_url


@pytest.fixture
def pushed(world, git):
    owner = world.user()
    repo = world.repo(owner, private=True)
    token = world.token(owner)
    src = git.new_repo("src")
    git.run("push", http_url(repo["full_name"], token), "main", cwd=src)
    return {"owner": owner, "repo": repo, "token": token, "src": src,
            "settings": f"/api/repos/{repo['full_name']}"}


def test_collaborator_roles(world, git, pushed):
    repo, api = pushed["repo"], pushed["owner"]["api"]
    friend = world.user()
    ftoken = world.token(friend)
    url = http_url(repo["full_name"], ftoken)
    assert "Repository not found" in git.run("ls-remote", url, check=False).stderr

    assert api.put(f"{pushed['settings']}/collaborators/{friend['username']}", json={"role": "read"}).status_code == 200
    git.run("clone", "-q", url, "friend")
    clone = os.path.join(git.root, "friend")
    git.commit(clone, "f.txt", "x\n")
    assert "denied" in git.run("push", "origin", "main", cwd=clone, check=False).stderr
    assert friend["api"].patch(pushed["settings"], json={"description": "x"}).status_code == 403

    api.put(f"{pushed['settings']}/collaborators/{friend['username']}", json={"role": "write"})
    git.run("push", "origin", "main", cwd=clone)
    assert friend["api"].patch(pushed["settings"], json={"description": "x"}).status_code == 403

    api.put(f"{pushed['settings']}/collaborators/{friend['username']}", json={"role": "admin"})
    assert friend["api"].patch(pushed["settings"], json={"description": "by friend"}).status_code == 200
    assert repo["full_name"] in [r["full_name"] for r in friend["api"].get("/api/repos").json()]

    api.delete(f"{pushed['settings']}/collaborators/{friend['username']}")
    assert "Repository not found" in git.run("ls-remote", url, check=False).stderr


def test_protected_branch_and_tag(git, pushed):
    api, src = pushed["owner"]["api"], pushed["src"]
    url = http_url(pushed["repo"]["full_name"], pushed["token"])
    assert api.post(f"{pushed['settings']}/protection", json={"kind": "branch", "pattern": "main"}).status_code == 201
    assert api.post(f"{pushed['settings']}/protection", json={"kind": "tag", "pattern": "v*"}).status_code == 201
    assert api.post(f"{pushed['settings']}/protection",
                    json={"kind": "branch", "pattern": "release/*", "min_push_role": "admin"}).status_code == 201

    git.commit(src, "a.txt", "1\n")
    git.run("push", url, "main", cwd=src)
    git.run("commit", "-q", "--amend", "-m", "rewritten", cwd=src)
    out = git.run("push", "--force", url, "main", cwd=src, check=False)
    assert "main is a protected branch: force pushes are not allowed" in out.stderr

    git.run("fetch", "-q", url, "main", cwd=src)
    git.run("reset", "-q", "--hard", "FETCH_HEAD", cwd=src)
    git.run("tag", "v1", cwd=src)
    git.run("push", url, "v1", cwd=src)
    git.commit(src, "b.txt", "2\n")
    git.run("tag", "-f", "v1", cwd=src)
    assert "tags can not be moved" in git.run("push", "--force", url, "v1", cwd=src, check=False).stderr
    assert "can't be deleted" in git.run("push", url, "--delete", "v1", cwd=src, check=False).stderr

    rules = api.get(f"{pushed['settings']}/protection").json()
    for r in rules:
        api.delete(f"{pushed['settings']}/protection/{r['id']}")
    git.run("push", "--force", url, "v1", cwd=src)


def test_admin_only_branch(world, git, pushed):
    api = pushed["owner"]["api"]
    friend = world.user()
    api.put(f"{pushed['settings']}/collaborators/{friend['username']}", json={"role": "write"})
    api.post(f"{pushed['settings']}/protection", json={"kind": "branch", "pattern": "release/*", "min_push_role": "admin"})
    src = pushed["src"]
    git.run("checkout", "-qb", "release/1.0", cwd=src)
    out = git.run("push", http_url(pushed["repo"]["full_name"], world.token(friend)), "release/1.0", cwd=src,
                  check=False)
    assert "only repository admins can push to it" in out.stderr
    git.run("push", http_url(pushed["repo"]["full_name"], pushed["token"]), "release/1.0", cwd=src)


def test_deploy_tokens(git, pushed):
    api, full = pushed["owner"]["api"], pushed["repo"]["full_name"]
    ro = api.post(f"{pushed['settings']}/deploy-tokens", json={"name": "server", "access": "read"}).json()
    rw = api.post(f"{pushed['settings']}/deploy-tokens", json={"name": "ci", "access": "write"}).json()
    assert ro["token"].startswith("mgd_")

    git.run("clone", "-q", http_url(full, ro["token"], user="deploy"), "server")
    server = os.path.join(git.root, "server")
    raw = requests.get(f"{BASE}/raw/{full}/main/README.md", auth=("deploy", ro["token"]), timeout=30)
    assert raw.text == "hello\n"
    git.commit(server, "x.txt", "x\n")
    assert "denied" in git.run("push", "origin", "main", cwd=server, check=False).stderr
    git.run("push", http_url(full, rw["token"], user="deploy"), "main", cwd=server)

    other = pushed["owner"]["api"].post("/api/repos", json={"name": "other-" + full.split("-")[-1], "private": True}).json()
    try:
        out = git.run("ls-remote", http_url(other["full_name"], ro["token"]), check=False)
        assert "Repository not found" in out.stderr
    finally:
        pushed["owner"]["api"].delete(f"/api/repos/{other['full_name']}")

    api.delete(f"{pushed['settings']}/deploy-tokens/{ro['id']}")
    assert "Authentication failed" in git.run("ls-remote", http_url(full, ro["token"]), check=False).stderr
    assert requests.get(f"{BASE}/api/repos/{full}", headers={"Authorization": f"token {rw['token']}"},
                        timeout=30).status_code == 200


def test_rename_keeps_old_urls_working(world, git, pushed):
    api, old = pushed["owner"]["api"], pushed["repo"]["full_name"]
    new_name = pushed["repo"]["name"] + "-renamed"
    r = api.patch(pushed["settings"], json={"name": new_name})
    assert r.status_code == 200 and r.json()["name"] == new_name
    git.run("clone", "-q", http_url(old, pushed["token"]), "via-old")
    assert api.get(f"/api/repos/{old}").json()["name"] == new_name
    raw = requests.get(f"{BASE}/raw/{old}/main/README.md", auth=("x", pushed["token"]), timeout=30)
    assert raw.text == "hello\n"
    world.repos[-1] = (pushed["owner"], {**pushed["repo"], "full_name": f"{pushed['owner']['username']}/{new_name}"})


def test_user_rename_and_transfer(world, git, admin, pushed):
    owner, repo = pushed["owner"], pushed["repo"]
    old_full = repo["full_name"]
    new_username = owner["username"] + "x"
    assert admin.patch(f"/api/admin/users/{owner['id']}", json={"username": new_username}).status_code == 200
    git.run("ls-remote", http_url(old_full, pushed["token"]))

    heir = world.user()
    r = owner["api"].post(f"/api/repos/{new_username}/{repo['name']}/transfer", json={"new_owner": heir["username"]})
    assert r.status_code == 200 and r.json()["owner"] == heir["username"]
    git.run("ls-remote", http_url(old_full, pushed["token"]))
    collaborators = heir["api"].get(f"/api/repos/{heir['username']}/{repo['name']}/collaborators").json()
    assert [(c["username"], c["role"]) for c in collaborators] == [(new_username, "admin")]
    world.repos[-1] = (heir, {**repo, "full_name": f"{heir['username']}/{repo['name']}"})


def test_archive_default_branch_and_visibility(git, pushed):
    api, src, full = pushed["owner"]["api"], pushed["src"], pushed["repo"]["full_name"]
    url = http_url(full, pushed["token"])
    git.run("checkout", "-qb", "develop", cwd=src)
    git.commit(src, "d.txt", "dev\n")
    git.run("push", url, "develop", cwd=src)

    assert api.patch(pushed["settings"], json={"default_branch": "develop"}).json()["default_branch"] == "develop"
    assert "ref: refs/heads/develop\tHEAD" in git.run("ls-remote", "--symref", url, "HEAD").stdout
    assert api.patch(pushed["settings"], json={"default_branch": "nope"}).status_code == 400

    api.patch(pushed["settings"], json={"archived": True})
    git.commit(src, "e.txt", "e\n")
    assert "archived" in git.run("push", url, "develop", cwd=src, check=False).stderr
    api.patch(pushed["settings"], json={"archived": False})
    git.run("push", url, "develop", cwd=src)

    api.patch(pushed["settings"], json={"private": False})
    git.run("ls-remote", http_url(full))
    api.patch(pushed["settings"], json={"private": True})
    assert "could not read Username" in git.run("ls-remote", http_url(full), check=False).stderr
