import logging

from flask import Flask, jsonify, request

import config
import db


def create_app():
    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY
    app.logger.setLevel(logging.INFO)
    app.config.update(
        SESSION_COOKIE_NAME="mygit_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=config.PUBLIC_URL.startswith("https://"),
        PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30,
        MAX_CONTENT_LENGTH=None,
    )

    db.run_migrations()

    import auth
    import internal_api
    import keys_api
    import repos_api
    import site_settings_api
    import tokens_api
    import users_api

    app.before_request(auth.load_user)
    for module in (auth, users_api, tokens_api, keys_api, repos_api, internal_api, site_settings_api):
        app.register_blueprint(module.bp)
    app.teardown_appcontext(db.close_db)

    @app.after_request
    def headers(response):
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.errorhandler(404)
    def not_found(_e):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(405)
    def not_allowed(_e):
        return jsonify({"error": f"{request.method} not allowed here"}), 405

    @app.get("/api/site")
    def site():
        import urls

        return jsonify({"base_url": urls.base_url(), "ssh_host": urls.ssh_host(), "ssh_port": config.SSH_PORT})

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    return app
