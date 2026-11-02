import logging
from flask import Flask, jsonify
from flask_cors import CORS
from config import Config
from api.routes import bp
from api.tasks import TaskStore
from api.errors import ApiError


def create_app(overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)
    app.config["MAX_CONTENT_LENGTH"] = app.config["MAX_UPLOAD_BYTES"] + 1_000_000
    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})
    app.extensions["tasks"] = TaskStore(app.config["MAX_TASKS"])
    app.register_blueprint(bp)
    logging.basicConfig(level=logging.INFO)

    def err(code, msg, status, details=None):
        return jsonify({"ok": False, "error": {"code": code, "message": msg, "details": details}}), status

    @app.errorhandler(ApiError)
    def _api(e):
        return err(e.code, e.message, e.status, e.details)

    @app.errorhandler(413)
    def _big(e):
        return err("file_too_large", "Upload exceeds the size limit.", 413)

    @app.errorhandler(404)
    def _nf(e):
        return err("not_found", "Endpoint not found.", 404)

    @app.errorhandler(405)
    def _mna(e):
        return err("method_not_allowed", "Method not allowed.", 405)

    @app.errorhandler(Exception)
    def _any(e):
        app.logger.exception("unhandled error")
        return err("internal_error", "An internal error occurred.", 500)

    return app
