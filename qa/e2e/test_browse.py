"""Browsing API, raw files and archives: what the web pages and the
installers (curl | bash) rely on."""

import io
import os
import subprocess
import tarfile
import zipfile

import pytest
import requests
from conftest import BASE, http_url

FILES = {
    "README.md": "# Demo\n\n![logo](docs/logo.png)\n\n[guide](docs/guide.md)\n\n<script>alert(1)</script>\n",
    "install.sh": "#!/usr/bin/env bash\nset -e\necho \"installed $1\"\n",
    "src/app.py": "def main():\n    return 'hi'\n",
    "docs/guide.md": "Guide\n",
    "docs/logo.png": b"\x89PNG\r\n\x1a\n" + bytes(range(256)),
    "evil.html": "<html><script>document.title='pwned'</script></html>\n",
    "evil.svg": "<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>\n",
    "data.bin": bytes(range(256)) * 10,
}


@pytest.fixture
def demo(world, git):
    owner = world.user()
    repo = world.repo(owner)
    token = world.token(owner)
    src = git.new_repo(files=FILES)
    url = http_url(repo["full_name"], token)
    git.run("push", url, "main", cwd=src)
    git.run("checkout", "-qb", "feature/new-ui", cwd=src)
    git.commit(src, "src/app.py", "def main():\n    return 'new'\n", "new ui")
    git.run("tag", "v1.0.0", "main", cwd=src)
    git.run("push", url, "feature/new-ui", "v1.0.0", cwd=src)
    return {"owner": owner, "repo": repo, "token": token, "src": src, "api": owner["api"],
            "base": f"/api/repos/{repo['full_name']}", "web": f"{BASE}/{repo['full_name']}",
            "rawtop": f"{BASE}/raw/{repo['full_name']}"}


def test_tree_readme_and_resolve(demo):
    api, base = demo["api"], demo["base"]
    root = api.get(f"{base}/tree").json()
    assert [e["name"] for e in root["entries"]] == ["docs", "src", "data.bin", "evil.html", "evil.svg", "install.sh",
                                                    "README.md"]
    assert '<img src="/{}/raw/main/docs/logo.png"'.format(demo["repo"]["full_name"]) in root["readme"]["html"]
    assert "<script>" not in root["readme"]["html"]
    resolved = api.get(f"{base}/resolve", params={"path": "feature/new-ui/src/app.py"}).json()
    assert resolved == {"ref": "feature/new-ui", "kind": "branch", "path": "src/app.py"}
    last = api.get(f"{base}/tree-commits", params={"path": "src", "ref": "feature/new-ui"}).json()
    assert last["app.py"]["subject"] == "new ui"


def test_blob_view(demo):
    api, base = demo["api"], demo["base"]
    py = api.get(f"{base}/blob", params={"path": "src/app.py"}).json()
    assert (py["language"], py["line_count"]) == ("Python", 2)
    assert py["lines"][0].startswith('<span class="k">def</span>')
    assert api.get(f"{base}/blob", params={"path": "data.bin"}).json()["binary"] is True
    assert api.get(f"{base}/blob", params={"path": "nope.txt"}).status_code == 404
    assert api.get(f"{base}/blob", params={"path": "../../etc/passwd"}).status_code == 400


def test_commits_commit_and_compare(demo):
    api, base = demo["api"], demo["base"]
    history = api.get(f"{base}/commits", params={"ref": "feature/new-ui", "path": "src/app.py"}).json()
    assert [c["subject"] for c in history["commits"]] == ["new ui", "initial"]
    head = history["commits"][0]["sha"]
    detail = api.get(f"{base}/commit/{head[:10]}").json()
    assert [(f["path"], f["additions"], f["deletions"]) for f in detail["diff"]["files"]] == [("src/app.py", 1, 1)]
    cmp = api.get(f"{base}/compare/main...feature/new-ui").json()
    assert [c["subject"] for c in cmp["commits"]] == ["new ui"]


@pytest.mark.parametrize("ref_form", ["main", "refs/heads/main", "v1.0.0"])
def test_raw_layouts(demo, ref_form):
    for url in (f"{demo['web']}/raw/{ref_form}/install.sh", f"{demo['rawtop']}/{ref_form}/install.sh"):
        r = requests.get(url, timeout=30)
        assert r.status_code == 200, url
        assert r.text == FILES["install.sh"]
        assert r.headers["Content-Type"] == "text/plain; charset=utf-8"


def test_raw_branch_with_slash_and_missing_paths(demo):
    r = requests.get(f"{demo['rawtop']}/feature/new-ui/src/app.py", timeout=30)
    assert r.text == "def main():\n    return 'new'\n"
    for missing in ("main/nope", "nope/install.sh", "main/src", "main/../../etc/passwd"):
        assert requests.get(f"{demo['rawtop']}/{missing}", timeout=30).status_code == 404, missing


def test_raw_never_renders_html_or_svg(demo):
    for name, expected in (("evil.html", "text/plain; charset=utf-8"), ("evil.svg", "image/svg+xml")):
        r = requests.get(f"{demo['web']}/raw/main/{name}", timeout=30)
        assert r.headers["Content-Type"] == expected
        assert "sandbox" in r.headers["Content-Security-Policy"]
        assert r.headers["X-Content-Type-Options"] == "nosniff"
    png = requests.get(f"{demo['web']}/raw/main/docs/logo.png", timeout=30)
    assert png.headers["Content-Type"] == "image/png" and png.content == FILES["docs/logo.png"]
    binary = requests.get(f"{demo['web']}/raw/main/data.bin", timeout=30)
    assert binary.headers["Content-Type"] == "application/octet-stream" and binary.content == FILES["data.bin"]


def test_raw_etag(demo):
    url = f"{demo['web']}/raw/main/install.sh"
    first = requests.get(url, timeout=30)
    again = requests.get(url, headers={"If-None-Match": first.headers["ETag"]}, timeout=30)
    assert again.status_code == 304


def test_curl_pipe_bash(demo):
    """The installer one-liner, exactly as people run it."""
    url = f"{demo['rawtop']}/main/install.sh"
    out = subprocess.run(["bash", "-c", f'bash <(curl -fsSL "{url}") myapp'], capture_output=True, text=True,
                         timeout=60)
    assert out.stdout == "installed myapp\n", out.stderr


def test_archives(demo):
    name = demo["repo"]["name"]
    r = requests.get(f"{demo['web']}/archive/refs/heads/main.tar.gz", timeout=60)
    assert r.headers["Content-Disposition"] == f'attachment; filename="{name}-main.tar.gz"'
    with tarfile.open(fileobj=io.BytesIO(r.content)) as tar:
        assert tar.extractfile(f"{name}-main/install.sh").read().decode() == FILES["install.sh"]
    z = requests.get(f"{demo['web']}/archive/v1.0.0.zip", timeout=60)
    with zipfile.ZipFile(io.BytesIO(z.content)) as zf:
        assert zf.read(f"{name}-v1.0.0/src/app.py").decode() == FILES["src/app.py"]
    assert requests.get(f"{demo['web']}/archive/nope.zip", timeout=30).status_code == 404


def test_private_raw_needs_a_token(world, git):
    owner = world.user()
    repo = world.repo(owner, private=True)
    token = world.token(owner, "read")
    git.run("push", http_url(repo["full_name"], world.token(owner)), "main",
            cwd=git.new_repo(files={"install.sh": "echo private\n"}))
    url = f"{BASE}/raw/{repo['full_name']}/main/install.sh"
    assert requests.get(url, timeout=30).status_code == 404
    assert requests.get(url, auth=("x", token), timeout=30).text == "echo private\n"
    assert requests.get(url, headers={"Authorization": f"token {token}"}, timeout=30).status_code == 200
    assert requests.get(url, auth=("x", "mgp_" + "Z" * 36), timeout=30).status_code == 401


def test_delete_branch_from_website(demo):
    api, base = demo["api"], demo["base"]
    assert api.delete(f"{base}/branches/main").status_code == 403
    assert api.delete(f"{base}/branches/feature/new-ui").status_code == 200
    names = [b["name"] for b in api.get(f"{base}/refs").json()["branches"]]
    assert names == ["main"]
