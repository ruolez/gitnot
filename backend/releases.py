"""Releases: GitHub-compatible JSON and the rules around tags and "latest".
Pure functions; releases_api.py does the I/O."""

import re
from urllib.parse import quote

ASSET_NAME_RE = re.compile(r"^[^/\\\x00-\x1f]{1,255}$")


def asset_name_error(name):
    if not isinstance(name, str) or not ASSET_NAME_RE.fullmatch(name) or name in (".", ".."):
        return "Asset names are 1-255 characters without slashes"
    return None


def tag_name_error(tag):
    """git's own rules for a tag name (check-ref-format), plus no leading '-'."""
    if not isinstance(tag, str) or not tag or len(tag) > 200:
        return "Give the release a tag, like v1.2.0"
    bad = (tag.startswith(("-", "/", ".")) or tag.endswith(("/", ".", ".lock")) or ".." in tag or "//" in tag
           or "@{" in tag or tag == "@" or any(c in tag for c in " ~^:?*[\\\x7f") or any(ord(c) < 32 for c in tag))
    return "That is not a valid tag name" if bad else None


def pick_latest(releases):
    """GitHub's /releases/latest: the newest published, non-draft,
    non-prerelease release that may be latest. None if there is none."""
    candidates = [r for r in releases if not r["draft"] and not r["prerelease"] and r["make_latest"]
                  and r["published_at"] is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda r: (r["published_at"], r["id"]))


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def asset_json(asset, base, full_name, tag):
    api = f"{base}/api/v1/repos/{full_name}"
    return {
        "id": asset["id"],
        "url": f"{api}/releases/assets/{asset['id']}",
        "browser_download_url": f"{base}/{full_name}/releases/download/{quote(tag, safe='/')}/{quote(asset['name'])}",
        "name": asset["name"],
        "label": asset["label"],
        "state": "uploaded",
        "content_type": asset["content_type"],
        "size": asset["size"],
        "digest": f"sha256:{asset['sha256']}",
        "download_count": asset["download_count"],
        "created_at": _iso(asset["created_at"]),
        "updated_at": _iso(asset["updated_at"]),
        "uploader": {"login": asset["uploader"]},
    }


def release_json(release, assets, base, full_name, author=""):
    """The fields GitHub's REST API returns that clients read (tag_name,
    draft, prerelease, assets[].browser_download_url ...)."""
    api = f"{base}/api/v1/repos/{full_name}"
    tag = release["tag_name"]
    return {
        "id": release["id"],
        "url": f"{api}/releases/{release['id']}",
        "html_url": f"{base}/{full_name}/releases/tag/{quote(tag, safe='/')}",
        "assets_url": f"{api}/releases/{release['id']}/assets",
        "upload_url": f"{api}/releases/{release['id']}/assets{{?name,label}}",
        "tarball_url": f"{base}/{full_name}/archive/{quote(tag, safe='/')}.tar.gz",
        "zipball_url": f"{base}/{full_name}/archive/{quote(tag, safe='/')}.zip",
        "tag_name": tag,
        "target_commitish": release["target_commitish"],
        "name": release["name"] or tag,
        "body": release["body"],
        "draft": release["draft"],
        "prerelease": release["prerelease"],
        "make_latest": release["make_latest"],
        "created_at": _iso(release["created_at"]),
        "published_at": _iso(release["published_at"]),
        "author": {"login": author},
        "assets": [asset_json(a, base, full_name, tag) for a in assets],
    }
