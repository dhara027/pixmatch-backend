"""
Events routes — /api/v1/events/*
All write endpoints require JWT authentication.
Event listing is filtered to the authenticated photographer (no IDOR).
"""
import logging

from flask import Blueprint, g, request, send_file
import io

from app.middleware.auth import require_auth
from app.modules.events.schemas import CreateEventSchema, EventListQuerySchema
from app.modules.events.service import event_service
from app.utils.response import created, no_content, paginated, success

logger = logging.getLogger(__name__)

events_bp = Blueprint("events", __name__)

_create_schema = CreateEventSchema()
_list_query_schema = EventListQuerySchema()


@events_bp.route("", methods=["POST"])
@require_auth
def create_event():
    data = _create_schema.load(request.get_json(force=True) or {})
    event, qr_bytes = event_service.create_event(
        photographer_id=g.user_id,
        photographer_name=data["photographer_name"],
        event_name=data["event_name"],
        event_location=data["event_location"],
        event_date=data["event_date"],
    )
    return created({"event": event, "qr_code_base64": _bytes_to_b64(qr_bytes)})


@events_bp.route("", methods=["GET"])
@require_auth
def list_events():
    query = _list_query_schema.load(request.args)
    events, total = event_service.list_events(
        photographer_id=g.user_id,
        page=query["page"],
        page_size=query["page_size"],
    )
    return paginated(events, query["page"], query["page_size"], total, data_key="events")


@events_bp.route("/<event_id>", methods=["GET"])
@require_auth
def get_event(event_id: str):
    event = event_service.get_event(event_id=event_id, photographer_id=g.user_id)
    return success({"event": event})


@events_bp.route("/<event_id>/public", methods=["GET"])
def get_event_public(event_id: str):
    """No auth — called by guest QR scan."""
    event = event_service.get_event_public(event_id=event_id)
    return success({"event": event})


@events_bp.route("/<event_id>/qr", methods=["GET"])
@require_auth
def download_qr(event_id: str):
    # Verify ownership before returning QR
    event_service.get_event(event_id=event_id, photographer_id=g.user_id)
    from app.config.settings import config
    qr_bytes = event_service.generate_qr_for_event(event_id)
    return send_file(
        io.BytesIO(qr_bytes),
        mimetype="image/png",
        as_attachment=True,
        download_name=f"event_{event_id}_qr.png",
    )


@events_bp.route("/<event_id>", methods=["DELETE"])
@require_auth
def delete_event(event_id: str):
    event_service.delete_event(event_id=event_id, photographer_id=g.user_id)
    return no_content()


def _bytes_to_b64(data: bytes) -> str:
    import base64
    return base64.b64encode(data).decode("utf-8")
