import json

from flask import g, jsonify, request


def api_error(message, status=400, **extra):
    body = {"error": message}
    body.update(extra)
    return jsonify(body), status


def client_ip():
    """nginx sets X-Real-IP; behind shared-proxy it carries the visitor's address."""
    return request.headers.get("X-Real-IP") or request.remote_addr or ""


def audit(action, details=None, user_id=None):
    import db

    if user_id is None:
        user = getattr(g, "user", None)
        user_id = user["id"] if user else None
    db.execute(
        "INSERT INTO audit_log (user_id, action, details, ip) VALUES (%s, %s, %s, %s)",
        (user_id, action, json.dumps(details or {}), client_ip()),
    )


def body():
    return request.get_json(silent=True) or {}
