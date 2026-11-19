"""Deciding git smart-HTTP requests. nginx asks /internal/git-auth before it
hands a request to git-http-backend; these helpers are the pure part."""

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, unquote, urlsplit

from permissions import at_least, can_push

_GIT_PATH = re.compile(r"^/([^/]+)/([^/]+?)(\.git)?/(info/refs|git-upload-pack|git-receive-pack)$")
SERVICES = ("git-upload-pack", "git-receive-pack")


@dataclass(frozen=True)
class GitRequest:
    owner: str
    repo: str
    service: str  # git-upload-pack | git-receive-pack
    endpoint: str  # info/refs | git-upload-pack | git-receive-pack

    @property
    def write(self):
        return self.service == "git-receive-pack"


def parse_git_request(uri):
    """GitRequest for a smart-HTTP URI such as
    /alice/app.git/info/refs?service=git-upload-pack, or None."""
    parts = urlsplit(uri)
    m = _GIT_PATH.match(unquote(parts.path))
    if not m:
        return None
    owner, repo, _suffix, endpoint = m.groups()
    if endpoint == "info/refs":
        service = (parse_qs(parts.query).get("service") or [""])[0]
        if service not in SERVICES:
            # Dumb-protocol fetch; git-http-backend would serve raw files. We only speak smart.
            return None
    else:
        service = endpoint
    return GitRequest(owner=owner, repo=repo, service=service, endpoint=endpoint)


@dataclass(frozen=True)
class Decision:
    status: int  # 200 allow, 401 ask for credentials, 403 refuse
    message: str = ""


def decide(req, repo, level, has_credentials):
    """repo: the repos row or None when no such repository is visible.
    level: repo_access() for the caller. has_credentials: whether the
    request carried a valid token (bad tokens are rejected before this)."""
    if repo is None or not at_least(level, "read"):
        # Anonymous callers are asked to sign in, so a private repository
        # looks the same as a missing one until they do.
        if not has_credentials:
            return Decision(401, "Authentication required")
        return Decision(403, "Repository not found")
    if req.write:
        if not has_credentials:
            return Decision(401, "Authentication required")
        if repo["archived"]:
            return Decision(403, "This repository is archived and read-only")
        if not can_push(repo, level):
            return Decision(403, f"Write access to {req.owner}/{repo['name']} denied")
    return Decision(200)


def pkt_line(text):
    data = text.encode()
    return b"%04x" % (len(data) + 4) + data


def error_advertisement(service, message):
    """A smart-HTTP info/refs reply that makes git print
    'fatal: remote error: <message>' instead of a bare HTTP status."""
    return pkt_line(f"# service={service}\n") + b"0000" + pkt_line(f"ERR {message}")
