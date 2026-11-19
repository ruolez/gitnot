from functools import wraps

from flask import Blueprint, g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

import config
import db
from util import api_error, audit, body, client_ip

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
MIN_PASSWORD = 8


def public_user(row):
    return {
        "id": row["id"],
        "username": row["username"],
        "full_name": row["full_name"],
        "email": row["email"],
        "is_admin": row["is_admin"],
    }


def _session_user():
    uid = session.get("user_id")
    if not uid:
        return None
    row = db.query("SELECT * FROM users WHERE id = %s AND is_active", (uid,), one=True)
    if not row:
        session.clear()
    return row


def load_user():
    """before_request: who is calling. Cookies for the web UI; an access token
    in Authorization for scripts and git. A request that sends a token is
    judged by the token alone, never by a cookie that rides along."""
    import credentials

    g.user = None
    g.principal = credentials.ANONYMOUS
    if request.path.startswith("/internal/"):
        return None
    header = request.headers.get("Authorization", "")
    if header:
        ip = client_ip()
        token = credentials.parse_authorization(header)
        principal = credentials.lookup(token) if token else None
        if principal is None:
            if too_many_failures(ip, "token"):
                return api_error("Too many failed attempts. Try again in a few minutes.", 429)
            record_failure(ip, "token")
            return api_error("Bad credentials", 401)
        g.principal = principal
        g.user = principal.user
        if request.method in UNSAFE_METHODS and principal.access == "read":
            return api_error("This token is read-only", 403)
        return None
    row = _session_user()
    if row:
        g.user = row
        g.principal = credentials.session_principal(row)
        # A page on another site can post a form with our cookie, but it can't
        # add a custom header without a CORS preflight we never answer.
        if request.method in UNSAFE_METHODS and request.headers.get("X-Requested-With") != "mygit":
            return api_error("Missing X-Requested-With header", 403)
    return None


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not g.user:
            return api_error("Not authenticated", 401)
        return f(*args, **kwargs)

    return wrapper


def admin_required(f):
    """Site administration happens in the browser; tokens can't reach it."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not g.user:
            return api_error("Not authenticated", 401)
        if not g.user["is_admin"] or g.principal.kind != "session":
            return api_error("Admin access required", 403)
        return f(*args, **kwargs)

    return wrapper


def session_required(f):
    """Account changes (password, tokens, keys) need the signed-in browser,
    not a token, so a leaked token can't mint more tokens."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not g.user:
            return api_error("Not authenticated", 401)
        if g.principal.kind != "session":
            return api_error("Sign in on the website to do this", 403)
        return f(*args, **kwargs)

    return wrapper


def too_many_failures(ip, kind="login"):
    """kind 'login' (passwords) or 'token'. Tokens are 214-bit random strings,
    so their limit only slows scanners down; it is applied to unknown tokens,
    never to a valid one."""
    limit = config.AUTH_FAILURE_LIMIT if kind == "login" else config.AUTH_FAILURE_LIMIT * 10
    row = db.query(
        """SELECT COUNT(*) AS n FROM auth_failures
           WHERE kind = %s AND ip = %s AND at > now() - make_interval(mins => %s)""",
        (kind, ip, config.AUTH_FAILURE_WINDOW_MIN),
        one=True,
    )
    return row["n"] >= limit


def record_failure(ip, kind="login"):
    db.execute("INSERT INTO auth_failures (ip, kind) VALUES (%s, %s)", (ip, kind))
    db.execute("DELETE FROM auth_failures WHERE at < now() - interval '1 day'")


def password_error(password):
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        return f"Passwords need at least {MIN_PASSWORD} characters"
    if len(password) > 512:
        return "Password is too long"
    return None


def hash_password(password):
    return generate_password_hash(password)


@bp.post("/login")
def login():
    ip = client_ip()
    if too_many_failures(ip):
        return api_error("Too many failed attempts. Try again in a few minutes.", 429)
    data = body()
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    user = db.query(
        "SELECT * FROM users WHERE lower(username) = lower(%s) AND is_active", (username,), one=True
    )
    if not user or not check_password_hash(user["password_hash"], password):
        record_failure(ip)
        return api_error("Invalid username or password", 401)
    session.clear()
    session.permanent = bool(data.get("remember"))
    session["user_id"] = user["id"]
    db.execute("UPDATE users SET last_login_at = now() WHERE id = %s", (user["id"],))
    audit("auth.login", {"remember": session.permanent}, user_id=user["id"])
    return jsonify(public_user(user))


@bp.post("/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@bp.get("/me")
@login_required
def me():
    return jsonify(public_user(g.user))


@bp.patch("/me")
@session_required
def update_me():
    data = body()
    full_name = str(data.get("full_name", g.user["full_name"]))[:200]
    email = str(data.get("email", g.user["email"])).strip()[:254]
    row = db.execute(
        "UPDATE users SET full_name = %s, email = %s WHERE id = %s RETURNING *",
        (full_name, email, g.user["id"]),
        returning=True,
    )
    return jsonify(public_user(row))


@bp.post("/me/password")
@session_required
def change_password():
    data = body()
    if not check_password_hash(g.user["password_hash"], str(data.get("current") or "")):
        return api_error("Current password is wrong", 400)
    new = data.get("new")
    err = password_error(new)
    if err:
        return api_error(err)
    db.execute("UPDATE users SET password_hash = %s WHERE id = %s", (hash_password(new), g.user["id"]))
    audit("auth.password_changed")
    return jsonify({"ok": True})
