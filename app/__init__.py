"""
Flask application factory.
Creates and configures the Flask app with all extensions, blueprints, and middleware.
"""
import logging
import logging.config
import os

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, jsonify
from flask_cors import CORS

from app.config.settings import config
from app.extensions.database import close_pool, init_db_pool
from app.extensions.limiter_ext import limiter
from app.extensions.redis_ext import init_redis
from app.middleware.error_handler import register_error_handlers
from app.middleware.security_headers import register_security_headers
from app.shared.cloudinary_client import init_cloudinary

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
                "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
            },
            "simple": {
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json" if config.FLASK_ENV == "production" else "simple",
            },
        },
        "root": {
            "level": "DEBUG" if config.DEBUG else "INFO",
            "handlers": ["console"],
        },
    })


def create_app() -> Flask:
    _configure_logging()

    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    # Per-file max is CLOUDINARY_MAX_FILE_BYTES (20 MB).
    # For a batch of up to 20 photos, set the Flask body limit accordingly.
    # This is validated again inside file_validator before any processing.
    app.config["MAX_CONTENT_LENGTH"] = config.CLOUDINARY_MAX_FILE_BYTES * 20
    app.config["FLASK_ENV"] = config.FLASK_ENV

    # ── CORS ─────────────────────────────────────────────────────────────────
    # supports_credentials=True is required for httpOnly cookie auth.
    # Origins must be explicit (not '*') when credentials are sent.
    CORS(
        app,
        resources={r"/api/*": {"origins": config.CORS_ORIGINS}},
        supports_credentials=True,
        allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
        expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining"],
    )

    # ── Rate Limiter ──────────────────────────────────────────────────────────
    app.config["RATELIMIT_STORAGE_URI"] = config.redis_url()
    app.config["RATELIMIT_DEFAULT_LIMITS"] = ["500 per day", "100 per hour"]
    app.config["RATELIMIT_HEADERS_ENABLED"] = True
    # Belt-and-suspenders: swallow storage errors so a Redis blip at startup
    # never causes health-probe failures (limiter_ext also sets fail_on_storage_error=False).
    app.config["RATELIMIT_SWALLOW_ERRORS"] = True
    limiter.init_app(app)

    # ── Extensions ────────────────────────────────────────────────────────────
    init_db_pool(config)
    init_redis()
    init_cloudinary()

    import atexit
    atexit.register(close_pool)

    # ── Middleware ────────────────────────────────────────────────────────────
    register_error_handlers(app)
    register_security_headers(app)

    # ── Blueprints (imported here to avoid circular import at module level) ──────
    from app.modules.auth.routes import auth_bp
    from app.modules.events.routes import events_bp
    from app.modules.face_match.routes import face_match_bp
    from app.modules.photos.routes import photos_bp

    limiter.limit("5 per minute; 30 per hour")(auth_bp)

    app.register_blueprint(auth_bp, url_prefix="/api/v1/auth")
    app.register_blueprint(events_bp, url_prefix="/api/v1/events")
    app.register_blueprint(photos_bp, url_prefix="/api/v1")
    app.register_blueprint(face_match_bp, url_prefix="/api/v1/face-match")

    # ── Health / Ping (Render probe endpoint) ────────────────────────────────
    # Must respond instantly with 200 — never probe DB/Redis here.
    # Render kills the deploy if this doesn't return 200 within its timeout.
    @app.route("/health")
    @limiter.exempt
    def health():
        return jsonify({"status": "ok", "service": "PixMatch API"}), 200

    @app.route("/ping")
    @limiter.exempt
    def ping():
        return "pong", 200

    # ── Serve React frontend (built dist/) ────────────────────────────────────
    # On Render: frontend is hosted on Vercel, dist/ is absent — serve API info.
    # Locally / Docker: dist/ is present — serve the SPA.
    from flask import send_file as _send_file

    FRONTEND_DIST = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..",
                     "PixMatch_frontend_1-main", "dist")
    )
    FRONTEND_INDEX = os.path.join(FRONTEND_DIST, "index.html")
    _frontend_available = os.path.isfile(FRONTEND_INDEX)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path):
        if not _frontend_available:
            return jsonify({
                "service": "PixMatch API",
                "status": "running",
                "docs": "Frontend hosted separately on Vercel",
            }), 200
        if path:
            candidate = os.path.normpath(os.path.join(FRONTEND_DIST, path))
            if candidate.startswith(FRONTEND_DIST + os.sep) and os.path.isfile(candidate):
                return _send_file(candidate)
        return _send_file(FRONTEND_INDEX)

    logger.info("Flask app created in %s mode.", config.FLASK_ENV)
    return app


# ── Celery App ────────────────────────────────────────────────────────────────
def create_celery(app: Flask = None):
    from celery import Celery

    celery = Celery(
        __name__,
        broker=config.celery_broker_url(),
        backend=config.celery_result_backend(),
    )
    celery.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_routes={
            "app.modules.face_match.tasks.compute_photo_embeddings_task": {"queue": "embeddings"},
            "app.modules.face_match.tasks.face_match_task": {"queue": "face_match"},
        },
    )
    return celery


celery_app = create_celery()
