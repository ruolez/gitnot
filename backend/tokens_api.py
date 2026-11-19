from datetime import datetime, timedelta, timezone

from flask import Blueprint, g, jsonify

import credentials
import db
from auth import session_required
from util import api_error, audit, body

bp = Blueprint("tokens", __name__, url_prefix="/api/user/tokens")


def token_json(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "prefix": row["prefix"],
        "access": row["access"],
        "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
        "created_at": row["created_at"].isoformat(),
        "last_used_at": row["last_used_at"].isoformat() if row["last_used_at"] else None,
    }


def parse_expiry(days):
    """None (never) or a datetime `days` from now; raises ValueError."""
    if days in (None, "", 0, "0", "never"):
        return None
    n = int(days)
    if not 1 <= n <= 3650:
        raise ValueError("Expiry must be 1-3650 days")
    return datetime.now(timezone.utc) + timedelta(days=n)


def mint_row(table, owner_col, owner_id, name, access, days, prefix, extra=None):
    """Create a token row; returns (row, plaintext). Shared with deploy tokens."""
    name = str(name or "").strip()[:100]
    if not name:
        raise ValueError("Give the token a name")
    if access not in ("read", "write"):
        raise ValueError("Access must be read or write")
    expires = parse_expiry(days)
    token = credentials.mint(prefix)
    cols = {owner_col: owner_id, "name": name, "token_hash": credentials.token_hash(token),
            "prefix": credentials.display_prefix(token), "access": access, "expires_at": expires, **(extra or {})}
    row = db.execute(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) RETURNING *",
        tuple(cols.values()), returning=True,
    )
    return row, token


@bp.get("")
@session_required
def list_tokens():
    rows = db.query("SELECT * FROM access_tokens WHERE user_id = %s ORDER BY created_at DESC", (g.user["id"],))
    return jsonify([token_json(r) for r in rows])


@bp.post("")
@session_required
def create_token():
    data = body()
    try:
        row, token = mint_row("access_tokens", "user_id", g.user["id"], data.get("name"),
                              data.get("access", "write"), data.get("expires_days"), credentials.PERSONAL_PREFIX)
    except ValueError as e:
        return api_error(str(e))
    audit("token.created", {"name": row["name"], "access": row["access"]})
    return jsonify({**token_json(row), "token": token}), 201


@bp.delete("/<int:token_id>")
@session_required
def delete_token(token_id):
    row = db.execute("DELETE FROM access_tokens WHERE id = %s AND user_id = %s RETURNING name",
                     (token_id, g.user["id"]), returning=True)
    if not row:
        return api_error("No such token", 404)
    audit("token.deleted", {"name": row["name"]})
    return jsonify({"ok": True})
