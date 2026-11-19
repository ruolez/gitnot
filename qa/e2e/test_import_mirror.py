"""Importing from another server and push mirrors, run by the worker. The
"other server" is this one (an admin setting allows internal remotes)."""

import time

import pytest
from conftest import BASE, http_url


@pytest.fixture
def internal_remotes(admin):
    before = admin.get("/api/admin/settings").json()["allow_internal_remotes"]
    admin.patch("/api/admin/settings", json={"allow_internal_remotes": True})
    yield
    admin.patch("/api/admin/settings", json={"allow_internal_remotes": before})


def wait_job(api, full_name, kind, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        jobs = [j for j in api.get(f"/api/repos/{full_name}/jobs").json() if j["kind"] == kind]
        if jobs and jobs[0]["status"] in ("done", "failed"):
            return jobs[0]
        time.sleep(0.5)
    raise AssertionError(f"{kind} job for {full_name} did not finish")


def test_internal_remotes_refused_by_default(world):
    user = world.user()
    r = user["api"].post("/api/repos/import", json={"url": f"{BASE}/x/y.git", "name": "imp"})
    assert r.status_code == 400 and "https" in r.json()["error"]


def test_import_private_repo_with_token(world, git, internal_remotes):
    owner = world.user()
    source = world.repo(owner, private=True)
    token = world.token(owner, "read")
    src = git.new_repo()
    git.run("checkout", "-qb", "develop", cwd=src)
    git.commit(src, "d.txt", "d\n")
    git.run("tag", "v1", cwd=src)
    git.run("push", http_url(source["full_name"], world.token(owner)), "main", "develop", "v1", cwd=src)

    r = owner["api"].post("/api/repos/import", json={"url": f"{BASE}/{source['full_name']}.git",
                                                     "name": source["name"] + "-copy", "token": token})
    assert r.status_code == 201, r.text
    copy = r.json()["repo"]
    world.repos.append((owner, copy))
    job = wait_job(owner["api"], copy["full_name"], "import")
    assert (job["status"], job["message"]) == ("done", "Imported 2 branches and 1 tag")
    assert git.run("ls-remote", http_url(copy["full_name"])).stdout == git.run("ls-remote", http_url(source["full_name"], token)).stdout
    info = owner["api"].get(f"/api/repos/{copy['full_name']}").json()
    assert (info["empty"], info["default_branch"]) == (False, "main")


def test_failed_import_reports_why(world, internal_remotes):
    owner = world.user()
    r = owner["api"].post("/api/repos/import", json={"url": f"{BASE}/{owner['username']}/missing.git", "name": "nothing"})
    repo = r.json()["repo"]
    world.repos.append((owner, repo))
    job = wait_job(owner["api"], repo["full_name"], "import")
    assert job["status"] == "failed" and job["message"]


def test_push_mirror(world, git, internal_remotes):
    owner = world.user()
    source, target = world.repo(owner), world.repo(owner, private=True)
    token = world.token(owner)
    r = owner["api"].put(f"/api/repos/{source['full_name']}/mirror",
                         json={"url": f"{BASE}/{target['full_name']}.git", "token": token})
    assert r.status_code == 200 and r.json()["has_token"] is True and "token" not in r.json()

    src = git.new_repo()
    git.run("push", http_url(source["full_name"], token), "main", cwd=src)
    sha = git.run("rev-parse", "HEAD", cwd=src).stdout.strip()
    job = wait_job(owner["api"], source["full_name"], "mirror")
    assert job["status"] == "done", job
    assert f"{sha}\trefs/heads/main" in git.run("ls-remote", http_url(target["full_name"], token)).stdout

    git.run("checkout", "-qb", "temp", cwd=src)
    git.run("push", http_url(source["full_name"], token), "temp", cwd=src)
    git.run("push", http_url(source["full_name"], token), "--delete", "temp", cwd=src)
    deadline = time.time() + 60
    while time.time() < deadline and "refs/heads/temp" in git.run("ls-remote", http_url(target["full_name"], token)).stdout:
        time.sleep(0.5)
    assert "refs/heads/temp" not in git.run("ls-remote", http_url(target["full_name"], token)).stdout
    mirror = owner["api"].get(f"/api/repos/{source['full_name']}/mirror").json()
    assert (mirror["last_status"], mirror["last_error"]) == ("ok", "")
