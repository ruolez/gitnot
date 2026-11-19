"""Access tokens: minting, hashing and reading them from an Authorization header.

Personal tokens (mgp_) act as their user, capped at the token's access.
Deploy tokens (mgd_) act on one repository only, with no user."""

import base64
import binascii
import hashlib
import secrets
import string
from dataclasses import dataclass
from typing import Optional

PERSONAL_PREFIX = "mgp_"
DEPLOY_PREFIX = "mgd_"
_ALPHABET = string.ascii_letters + string.digits
_BODY_LEN = 36


def mint(prefix):
    """A new token string, e.g. mgp_3kT…; 36 random base62 chars ≈ 214 bits."""
    return prefix + "".join(secrets.choice(_ALPHABET) for _ in range(_BODY_LEN))


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def display_prefix(token):
    return token[: len(PERSONAL_PREFIX) + 6]


def looks_like_token(value):
    return (
        isinstance(value, str)
        and value[:4] in (PERSONAL_PREFIX, DEPLOY_PREFIX)
        and len(value) == 4 + _BODY_LEN
        and all(c in _ALPHABET for c in value[4:])
    )


def parse_authorization(header):
    """The token in an Authorization header, or None when there is none.

    Accepts `Bearer <t>`, `token <t>` and HTTP Basic with the token as the
    password (git and curl -u send this; the username is ignored) or, for
    tools that only fill the username, as the username."""
    if not header:
        return None
    scheme, _, value = header.strip().partition(" ")
    scheme = scheme.lower()
    value = value.strip()
    if scheme in ("bearer", "token"):
        return value or None
    if scheme == "basic":
        try:
            decoded = base64.b64decode(value, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return None
        user, _, password = decoded.partition(":")
        if looks_like_token(password):
            return password
        if looks_like_token(user) and password in ("", "x-oauth-basic"):
            return user
        return password or None
    return None


@dataclass(frozen=True)
class Principal:
    """Who is acting. user is a users row (None for deploy tokens and anonymous)."""
    user: Optional[dict]
    access: str  # "read" | "write" | "admin" (sessions and anonymous: no cap)
    kind: str  # "session" | "personal" | "deploy" | "anonymous"
    token_id: Optional[int] = None
    deploy_repo_id: Optional[int] = None

    @property
    def username(self):
        return self.user["username"] if self.user else ("deploy-token" if self.kind == "deploy" else "")


ANONYMOUS = Principal(user=None, access="admin", kind="anonymous")


def session_principal(user):
    return Principal(user=user, access="admin", kind="session")


def lookup(token):
    """The Principal for a token string, or None if it is unknown, expired or
    its user is inactive. Touches last_used_at at most once a minute."""
    import db

    if not looks_like_token(token):
        return None
    digest = token_hash(token)
    if token.startswith(PERSONAL_PREFIX):
        row = db.query(
            """SELECT t.id AS token_id, t.access, t.last_used_at, u.*
               FROM access_tokens t JOIN users u ON u.id = t.user_id
               WHERE t.token_hash = %s AND u.is_active
                 AND (t.expires_at IS NULL OR t.expires_at > now())""",
            (digest,),
            one=True,
        )
        if not row:
            return None
        db.execute(
            """UPDATE access_tokens SET last_used_at = now()
               WHERE id = %s AND (last_used_at IS NULL OR last_used_at < now() - interval '1 minute')""",
            (row["token_id"],),
        )
        user = {k: row[k] for k in row if k not in ("token_id", "access", "last_used_at")}
        return Principal(user=user, access=row["access"], kind="personal", token_id=row["token_id"])
    row = db.query(
        """SELECT id, repo_id, access FROM deploy_tokens
           WHERE token_hash = %s AND (expires_at IS NULL OR expires_at > now())""",
        (digest,),
        one=True,
    )
    if not row:
        return None
    db.execute(
        """UPDATE deploy_tokens SET last_used_at = now()
           WHERE id = %s AND (last_used_at IS NULL OR last_used_at < now() - interval '1 minute')""",
        (row["id"],),
    )
    return Principal(user=None, access=row["access"], kind="deploy", token_id=row["id"],
                     deploy_repo_id=row["repo_id"])
