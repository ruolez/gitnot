"""Releases: the GitHub-compatible API that updaters read, uploads and
downloads (incl. resume), drafts, "latest", and the mygit CLI."""

import hashlib
import os
import subprocess

import pytest
import requests
from conftest import BASE, http_url, local


@pytest.fixture
def project(world, git):
    owner = world.user()
    repo = world.repo(owner)
    token = world.token(owner)
    git.run("push", http_url(repo["full_name"], token), "main", cwd=git.new_repo())
    api = f"{BASE}/api/v1/repos/{repo['full_name']}"
    return {"owner": owner, "repo": repo, "token": token, "api": api,
            "auth": {"Authorization": f"token {token}"}}


def create(p, **fields):
    r = requests.post(f"{p['api']}/releases", json=fields, headers=p["auth"], timeout=30)
    assert r.status_code == 201, r.text
    return r.json()


def upload(p, release, name, data):
    r = requests.post(f"{p['api']}/releases/{release['id']}/assets", params={"name": name}, data=data,
                      headers={**p["auth"], "Content-Type": "application/octet-stream"}, timeout=120)
    assert r.status_code == 201, r.text
    return r.json()


def test_github_compatible_feed_and_downloads(project):
    p = project
    rel = create(p, tag_name="v1.0.0", name="One", body="first")
    payload = os.urandom(5 * 1024 * 1024)
    asset = upload(p, rel, "app-1.0.0.zip", payload)
    assert asset["digest"] == "sha256:" + hashlib.sha256(payload).hexdigest()

    feed = requests.get(f"{p['api']}/releases?per_page=30", timeout=30).json()
    assert [(r["tag_name"], r["draft"], r["prerelease"]) for r in feed] == [("v1.0.0", False, False)]
    url = local(feed[0]["assets"][0]["browser_download_url"])
    assert url == f"{BASE}/{p['repo']['full_name']}/releases/download/v1.0.0/app-1.0.0.zip"
    got = requests.get(url, timeout=60)
    assert got.content == payload
    assert got.headers["Content-Disposition"] == 'attachment; filename="app-1.0.0.zip"'

    resumed = requests.get(url, headers={"Range": "bytes=1000-"}, timeout=60)
    assert resumed.status_code == 206 and resumed.content == payload[1000:]
    latest = requests.get(f"{BASE}/{p['repo']['full_name']}/releases/latest/download/app-1.0.0.zip", timeout=60)
    assert latest.content == payload
    count = requests.get(f"{p['api']}/releases/tags/v1.0.0", timeout=30).json()["assets"][0]["download_count"]
    assert count == 3


def test_latest_rules(project):
    p = project
    assert requests.get(f"{p['api']}/releases/latest", timeout=30).status_code == 404
    create(p, tag_name="v1.0.0")
    create(p, tag_name="v1.1.0-windows", make_latest="false")
    create(p, tag_name="v2.0.0-beta", prerelease=True)
    create(p, tag_name="v3.0.0", draft=True)
    assert requests.get(f"{p['api']}/releases/latest", timeout=30).json()["tag_name"] == "v1.0.0"
    public = [r["tag_name"] for r in requests.get(f"{p['api']}/releases", timeout=30).json()]
    assert "v3.0.0" not in public and set(public) == {"v1.0.0", "v1.1.0-windows", "v2.0.0-beta"}
    mine = [r["tag_name"] for r in requests.get(f"{p['api']}/releases", headers=p["auth"], timeout=30).json()]
    assert "v3.0.0" in mine


def test_tag_is_created_on_publish_not_on_draft(project, git):
    p = project
    draft = create(p, tag_name="v5.0.0", draft=True)
    refs = git.run("ls-remote", http_url(p["repo"]["full_name"])).stdout
    assert "refs/tags/v5.0.0" not in refs
    r = requests.patch(f"{p['api']}/releases/{draft['id']}", json={"draft": False}, headers=p["auth"], timeout=30)
    assert r.json()["published_at"] is not None
    assert "refs/tags/v5.0.0" in git.run("ls-remote", http_url(p["repo"]["full_name"])).stdout


def test_refusals(world, project):
    p = project
    rel = create(p, tag_name="v1.0.0")
    assert requests.post(f"{p['api']}/releases", json={"tag_name": "v1.0.0"}, headers=p["auth"],
                         timeout=30).status_code == 422
    assert requests.post(f"{p['api']}/releases", json={"tag_name": "bad tag"}, headers=p["auth"],
                         timeout=30).status_code == 422
    assert requests.post(f"{p['api']}/releases", json={"tag_name": "v9"}, timeout=30).status_code == 401
    read = world.token(p["owner"], "read")
    assert requests.post(f"{p['api']}/releases", json={"tag_name": "v9"},
                         headers={"Authorization": f"token {read}"}, timeout=30).status_code == 403
    stranger = world.token(world.user())
    assert requests.post(f"{p['api']}/releases", json={"tag_name": "v9"},
                         headers={"Authorization": f"token {stranger}"}, timeout=30).status_code == 403
    upload(p, rel, "a.zip", b"x")
    dup = requests.post(f"{p['api']}/releases/{rel['id']}/assets", params={"name": "a.zip"}, data=b"y",
                        headers=p["auth"], timeout=30)
    assert dup.status_code == 422 and dup.json()["code"] == "already_exists"
    bad = requests.post(f"{p['api']}/releases/{rel['id']}/assets", params={"name": "../x"}, data=b"y",
                        headers=p["auth"], timeout=30)
    assert bad.status_code == 422


def test_asset_size_limit(admin, project):
    p = project
    rel = create(p, tag_name="v1")
    before = admin.get("/api/admin/settings").json()["max_asset_mb"]
    admin.patch("/api/admin/settings", json={"max_asset_mb": 1})
    try:
        r = requests.post(f"{p['api']}/releases/{rel['id']}/assets", params={"name": "big.bin"},
                          data=os.urandom(2 * 1024 * 1024), headers=p["auth"], timeout=60)
        assert r.status_code == 413
    finally:
        admin.patch("/api/admin/settings", json={"max_asset_mb": before})


def test_private_release_with_deploy_token(world, git):
    owner = world.user()
    repo = world.repo(owner, private=True)
    token = world.token(owner)
    git.run("push", http_url(repo["full_name"], token), "main", cwd=git.new_repo())
    p = {"api": f"{BASE}/api/v1/repos/{repo['full_name']}", "auth": {"Authorization": f"token {token}"}}
    rel = create(p, tag_name="v1.0.0")
    asset = upload(p, rel, "agent.msi", b"private build")
    deploy = owner["api"].post(f"/api/repos/{repo['full_name']}/deploy-tokens",
                               json={"name": "updater", "access": "read"}).json()["token"]
    dl = local(asset["browser_download_url"])
    assert requests.get(dl, timeout=30).status_code == 404
    assert requests.get(f"{p['api']}/releases/latest", timeout=30).status_code == 404
    assert requests.get(dl, auth=("deploy", deploy), timeout=30).content == b"private build"
    via_api = requests.get(local(asset["url"]), headers={"Authorization": f"token {deploy}",
                                                  "Accept": "application/octet-stream"}, timeout=30)
    assert via_api.content == b"private build"


def test_delete_release_removes_files(project):
    p = project
    rel = create(p, tag_name="v1")
    asset = upload(p, rel, "a.bin", b"abc")
    assert requests.delete(f"{p['api']}/releases/{rel['id']}", headers=p["auth"], timeout=30).status_code == 204
    assert requests.get(local(asset["browser_download_url"]), timeout=30).status_code == 404
    assert requests.get(f"{p['api']}/releases/tags/v1", timeout=30).status_code == 404


def test_cli_release_flow(project, tmp_path):
    """The CLI as downloaded from the server, the way release scripts use it."""
    p = project
    cli = tmp_path / "mygit"
    cli.write_bytes(requests.get(f"{BASE}/cli/mygit", timeout=30).content)
    files = []
    for name, data in (("VS-Gammon-2.0.0-windows-x64.zip", b"zip"), ("VS-Gammon-2.0.0-windows-x64.zip.sig", b"sig")):
        f = tmp_path / name
        f.write_bytes(data)
        files.append(str(f))
    env = {**os.environ, "MYGIT_URL": BASE, "MYGIT_TOKEN": p["token"], "HOME": str(tmp_path)}
    run = lambda *a: subprocess.run(["python3", str(cli), *a], capture_output=True, text=True, env=env, timeout=120)
    out = run("release", "create", p["repo"]["full_name"], "v2.0.0-windows", *files, "--notes", "win", "--latest=false")
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().endswith("/releases/tag/v2.0.0-windows")
    listing = run("release", "list", p["repo"]["full_name"])
    assert listing.stdout.startswith("v2.0.0-windows\tv2.0.0-windows\t") and "2 assets" in listing.stdout
    again = run("release", "upload", p["repo"]["full_name"], "v2.0.0-windows", files[0])
    assert again.returncode == 1 and "--clobber" in again.stderr
    assert run("release", "upload", p["repo"]["full_name"], "v2.0.0-windows", files[0], "--clobber").returncode == 0
    dl = tmp_path / "dl"
    assert run("release", "download", p["repo"]["full_name"], "v2.0.0-windows", "--dir", str(dl)).returncode == 0
    assert (dl / "VS-Gammon-2.0.0-windows-x64.zip.sig").read_bytes() == b"sig"
    assert requests.get(f"{p['api']}/releases/latest", timeout=30).status_code == 404
    assert run("release", "delete", p["repo"]["full_name"], "v2.0.0-windows").returncode == 0
