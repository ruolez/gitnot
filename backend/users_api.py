from flask import Blueprint, g, jsonify

import db
from auth import admin_required, hash_password, password_error, public_user
from names import username_error
from util import api_error, audit, body

bp = Blueprint("users", __name__, url_prefix="/api/admin/users")


def _admin_row(row):
    out = public_user(row)
    out.update(is_active=row["is_active"], created_at=row["created_at"].isoformat(),
               last_login_at=row["last_login_at"].isoformat() if row["last_login_at"] else None)
    return out


def _name_taken(username, except_id=None):
    row = db.query(
        "SELECT id FROM users WHERE lower(username) = lower(%s) AND id IS DISTINCT FROM %s",
        (username, except_id),
        one=True,
    )
    return row is not None


@bp.get("")
@admin_required
def list_users():
    rows = db.query("SELECT * FROM users ORDER BY lower(username)")
    return jsonify([_admin_row(r) for r in rows])


@bp.post("")
@admin_required
def create_user():
    data = body()
    username = str(data.get("username") or "").strip()
    err = username_error(username) or password_error(data.get("password"))
    if err:
        return api_error(err)
    if _name_taken(username):
        return api_error("That username is taken", 409)
    row = db.execute(
        """INSERT INTO users (username, full_name, email, password_hash, is_admin)
           VALUES (%s, %s, %s, %s, %s) RETURNING *""",
        (username, str(data.get("full_name") or "")[:200], str(data.get("email") or "").strip()[:254],
         hash_password(data["password"]), bool(data.get("is_admin"))),
        returning=True,
    )
    audit("user.created", {"user": username})
    return jsonify(_admin_row(row)), 201


@bp.patch("/<int:user_id>")
@admin_required
def update_user(user_id):
    row = db.query("SELECT * FROM users WHERE id = %s", (user_id,), one=True)
    if not row:
        return api_error("No such user", 404)
    data = body()
    fields = {}
    if "username" in data:
        username = str(data["username"] or "").strip()
        err = username_error(username)
        if err:
            return api_error(err)
        if _name_taken(username, user_id):
            return api_error("That username is taken", 409)
        fields["username"] = username
    for key, limit in (("full_name", 200), ("email", 254)):
        if key in data:
            fields[key] = str(data[key] or "").strip()[:limit]
    for key in ("is_admin", "is_active"):
        if key in data:
            fields[key] = bool(data[key])
    if "password" in data:
        err = password_error(data["password"])
        if err:
            return api_error(err)
        fields["password_hash"] = hash_password(data["password"])
    if user_id == g.user["id"] and (fields.get("is_admin") is False or fields.get("is_active") is False):
        return api_error("You can't remove your own admin access or deactivate yourself")
    if not fields:
        return jsonify(_admin_row(row))
    sets = ", ".join(f"{k} = %s" for k in fields)
    row = db.execute(f"UPDATE users SET {sets} WHERE id = %s RETURNING *",
                     (*fields.values(), user_id), returning=True)
    audit("user.updated", {"user": row["username"], "fields": sorted(k for k in fields if k != "password_hash")
                           + (["password"] if "password_hash" in fields else [])})
    return jsonify(_admin_row(row))


@bp.delete("/<int:user_id>")
@admin_required
def delete_user(user_id):
    if user_id == g.user["id"]:
        return api_error("You can't delete yourself")
    row = db.query("SELECT * FROM users WHERE id = %s", (user_id,), one=True)
    if not row:
        return api_error("No such user", 404)
    db.execute("DELETE FROM users WHERE id = %s", (user_id,))
    audit("user.deleted", {"user": row["username"]})
    return jsonify({"ok": True})
