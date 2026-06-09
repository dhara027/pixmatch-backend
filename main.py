"""
WSGI entry point. Use with gunicorn:
  gunicorn -c gunicorn.conf.py "main:application"
"""
import sys
import traceback

from dotenv import load_dotenv
load_dotenv()

_startup_error = None

try:
    from app import create_app
    application = create_app()
except Exception as _exc:
    _startup_error = _exc
    traceback.print_exc()
    # Fallback: minimal Flask app so Render health probe gets 200
    # and the actual error is visible at /health for diagnosis.
    from flask import Flask, jsonify
    _fallback = Flask(__name__)

    @_fallback.route("/health")
    def health():
        return jsonify({
            "status": "startup_failed",
            "error": str(_startup_error),
            "type": type(_startup_error).__name__,
        }), 200

    @_fallback.route("/ping")
    def ping():
        return "pong", 200

    @_fallback.route("/", defaults={"path": ""})
    @_fallback.route("/<path:path>")
    def catch_all(path):
        return jsonify({
            "status": "startup_failed",
            "error": str(_startup_error),
        }), 503

    application = _fallback

if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 5000))
    application.run(host="0.0.0.0", port=port, debug=False)
