"""
Global error handlers.
Never exposes internal exception strings, stack traces, or database details.
"""
import logging

from flask import Flask, jsonify
from marshmallow import ValidationError as MarshmallowValidationError

from app.shared.exceptions import AppError

logger = logging.getLogger(__name__)


def register_error_handlers(app: Flask) -> None:

    @app.errorhandler(AppError)
    def handle_app_error(exc: AppError):
        logger.warning("AppError [%s]: %s", exc.code, exc.message)
        return jsonify({
            "success": False,
            "error": {"code": exc.code, "message": exc.message},
        }), exc.status_code

    @app.errorhandler(MarshmallowValidationError)
    def handle_validation_error(exc: MarshmallowValidationError):
        # Flatten Marshmallow messages into a list of {field, issue} pairs
        details = [
            {"field": field, "issue": "; ".join(msgs) if isinstance(msgs, list) else str(msgs)}
            for field, msgs in exc.messages.items()
        ]
        return jsonify({
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": details,
            },
        }), 400

    @app.errorhandler(404)
    def handle_404(_):
        return jsonify({
            "success": False,
            "error": {"code": "NOT_FOUND", "message": "The requested resource was not found"},
        }), 404

    @app.errorhandler(405)
    def handle_405(_):
        return jsonify({
            "success": False,
            "error": {"code": "METHOD_NOT_ALLOWED", "message": "Method not allowed"},
        }), 405

    @app.errorhandler(429)
    def handle_429(_):
        return jsonify({
            "success": False,
            "error": {"code": "RATE_LIMIT_EXCEEDED", "message": "Too many requests. Please slow down."},
        }), 429

    @app.errorhandler(Exception)
    def handle_generic(exc: Exception):
        # Log full traceback internally, return generic message externally
        logger.exception("Unhandled exception: %s", exc)
        return jsonify({
            "success": False,
            "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred. Please try again later."},
        }), 500
