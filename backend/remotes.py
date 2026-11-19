"""Talking to other git servers (imports, push mirrors): which URLs are
allowed, how credentials travel, and mapping GitHub's releases."""

import base64
import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit


class RemoteError(ValueError):
    pass


def _is_internal(address):
    ip = ipaddress.ip_address(address)
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified


def check_remote_url(url, resolve=socket.getaddrinfo, allow_internal=False):
    """The URL without credentials, or RemoteError. Only https, and never an
    address inside this network: an import must not become a way to read the
    backend, the database or the cloud metadata service. An admin can allow
    internal (and plain http) servers in Site admin > Settings."""
    parts = urlsplit((url or "").strip())
    schemes = ("https", "http") if allow_internal else ("https",)
    if parts.scheme not in schemes or not parts.hostname:
        raise RemoteError("Use an https:// URL, like https://github.com/owner/repo.git")
    if parts.username or parts.password:
        raise RemoteError("Put the token in the token field, not in the URL")
    if not allow_internal:
        try:
            infos = resolve(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)
        except (socket.gaierror, UnicodeError):
            raise RemoteError(f"Can't find the server {parts.hostname}") from None
        if any(_is_internal(info[4][0]) for info in infos):
            raise RemoteError(f"{parts.hostname} is on an internal network")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def internal_allowed():
    import db

    return db.get_setting("allow_internal_remotes", "0") == "1"


def git_env(username, token, allow_http=False):
    """Environment for talking to a remote: https only, no credential helper,
    and the token as an HTTP header passed through GIT_CONFIG_* variables, so
    it never lands on disk, in a URL or in the process list."""
    config = [("protocol.allow", "never"), ("protocol.https.allow", "always"), ("credential.helper", "")]
    if allow_http:
        config.append(("protocol.http.allow", "always"))
    if token:
        basic = base64.b64encode(f"{username or 'x-access-token'}:{token}".encode()).decode()
        config.append(("http.extraHeader", f"Authorization: Basic {basic}"))
    env = {"GIT_CONFIG_COUNT": str(len(config)), "GIT_TERMINAL_PROMPT": "0"}
    for i, (key, value) in enumerate(config):
        env[f"GIT_CONFIG_KEY_{i}"] = key
        env[f"GIT_CONFIG_VALUE_{i}"] = value
    return env


def github_repo(url):
    """(owner, repo) for a github.com URL, else None."""
    parts = urlsplit(url)
    if parts.hostname not in ("github.com", "www.github.com"):
        return None
    bits = [b for b in parts.path.split("/") if b]
    if len(bits) < 2:
        return None
    name = bits[1][:-4] if bits[1].endswith(".git") else bits[1]
    return bits[0], name


def latest_flags(releases, latest_tag):
    """GitHub decides "latest" itself (make_latest isn't in its API). Mark the
    newer stable releases that GitHub did not make latest as make_latest=false
    (side builds like v1.6.2-windows), so mygit's "latest" stays the same."""
    latest = next((r for r in releases if r["tag_name"] == latest_tag), None)
    flags = {}
    for r in releases:
        newer = latest is not None and (r.get("published_at") or "") > (latest.get("published_at") or "")
        flags[r["tag_name"]] = not (newer and not r.get("prerelease") and not r.get("draft"))
    return flags
