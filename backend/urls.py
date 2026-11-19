from urllib.parse import quote, urlsplit

from flask import has_request_context, request

import config


def base_url():
    """https://git.example.com, from PUBLIC_URL or the current request."""
    if config.PUBLIC_URL:
        return config.PUBLIC_URL
    if has_request_context():
        proto = request.headers.get("X-Forwarded-Proto", request.scheme)
        return f"{proto}://{request.host}"
    return ""


def ssh_host():
    if config.SSH_HOST:
        return config.SSH_HOST
    return urlsplit(base_url()).hostname or "localhost"


def repo_path(owner, name):
    return f"/{quote(owner)}/{quote(name)}"


def clone_urls(owner, name):
    host = ssh_host()
    if config.SSH_PORT == 22:
        ssh = f"git@{host}:{owner}/{name}.git"
    else:
        ssh = f"ssh://git@{host}:{config.SSH_PORT}/{owner}/{name}.git"
    return {"https": f"{base_url()}{repo_path(owner, name)}.git", "ssh": ssh}
