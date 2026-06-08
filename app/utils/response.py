"""
Standardized API response helpers.
All responses follow: { success, data/error, meta, timestamp }
"""
from datetime import datetime, timezone
from typing import Any, Optional
from flask import jsonify


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def success(data: Any = None, meta: Optional[dict] = None, status: int = 200):
    """Return a successful JSON response."""
    body: dict = {"success": True, "timestamp": _now()}
    if data is not None:
        body["data"] = data
    if meta:
        body["meta"] = meta
    return jsonify(body), status


def created(data: Any = None, meta: Optional[dict] = None):
    return success(data=data, meta=meta, status=201)


def no_content():
    # RFC 7231 §6.3.5: 204 No Content MUST NOT include a message body.
    return "", 204


def error(message: str, code: str = "ERROR", status: int = 400, details: Optional[list] = None):
    """Return a structured error JSON response."""
    body: dict = {
        "success": False,
        "error": {
            "code": code,
            "message": message,
        },
        "timestamp": _now(),
    }
    if details:
        body["error"]["details"] = details
    return jsonify(body), status


def paginated(items: list, page: int, page_size: int, total: int, data_key: str = "items"):
    total_pages = max(1, (total + page_size - 1) // page_size)
    return success(
        data={data_key: items},
        meta={
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
        },
    )
