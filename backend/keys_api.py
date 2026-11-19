from flask import Blueprint, g, jsonify

import db
from auth import session_required
from sshkeys import KeyError_, parse_public_key
from util import api_error, audit, body

bp = Blueprint("keys", __name__, url_prefix="/api/user/keys")


def key_json(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "key_type": row["key_type"],
        "fingerprint": row["fingerprint"],
        "created_at": row["created_at"].isoformat(),
        "last_used_at": row["last_used_at"].isoformat() if row["last_used_at"] else None,
    }


@bp.get("")
@session_required
def list_keys():
    rows = db.query("SELECT * FROM ssh_keys WHERE user_id = %s ORDER BY created_at DESC", (g.user["id"],))
    return jsonify([key_json(r) for r in rows])


@bp.post("")
@session_required
def add_key():
    data = body()
    try:
        key = parse_public_key(data.get("key"))
    except KeyError_ as e:
        return api_error(str(e))
    title = str(data.get("title") or key.comment or key.key_type).strip()[:100]
    if db.query("SELECT 1 FROM ssh_keys WHERE fingerprint = %s", (key.fingerprint,), one=True):
        return api_error("This key is already in use, on your account or someone else's", 409)
    row = db.execute(
        """INSERT INTO ssh_keys (user_id, title, key_type, key_blob, fingerprint)
           VALUES (%s, %s, %s, %s, %s) RETURNING *""",
        (g.user["id"], title, key.key_type, key.blob, key.fingerprint),
        returning=True,
    )
    audit("ssh_key.added", {"title": title, "fingerprint": key.fingerprint})
    return jsonify(key_json(row)), 201


@bp.delete("/<int:key_id>")
@session_required
def delete_key(key_id):
    row = db.execute("DELETE FROM ssh_keys WHERE id = %s AND user_id = %s RETURNING title, fingerprint",
                     (key_id, g.user["id"]), returning=True)
    if not row:
        return api_error("No such key", 404)
    audit("ssh_key.deleted", {"title": row["title"], "fingerprint": row["fingerprint"]})
    return jsonify({"ok": True})
