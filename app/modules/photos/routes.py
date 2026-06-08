"""
Photos routes — /api/v1/events/<event_id>/photos
"""
import logging
from marshmallow import Schema, fields, validate

from flask import Blueprint, g, request

from app.middleware.auth import require_auth
from app.modules.photos.service import photo_service
from app.utils.response import created, paginated

logger = logging.getLogger(__name__)

photos_bp = Blueprint("photos", __name__)


class PhotoListQuerySchema(Schema):
    page = fields.Int(load_default=1, validate=validate.Range(min=1))
    page_size = fields.Int(load_default=20, validate=validate.Range(min=1, max=100))


_list_schema = PhotoListQuerySchema()


@photos_bp.route("/events/<event_id>/photos", methods=["POST"])
@require_auth
def upload_photos(event_id: str):
    logger.debug(
        "Upload — Content-Type: %s | files: %s",
        request.content_type,
        list(request.files.keys()),
    )
    files = request.files.getlist("files")
    if not files:
        from app.utils.response import error
        return error("At least one file is required.", code="VALIDATION_ERROR")

    result = photo_service.upload_event_photos(
        event_id=event_id,
        photographer_id=g.user_id,
        files=files,
    )
    return created(result)


@photos_bp.route("/events/<event_id>/photos", methods=["GET"])
@require_auth
def list_photos(event_id: str):
    query = _list_schema.load(request.args)
    photos, total = photo_service.list_photos(
        event_id=event_id,
        photographer_id=g.user_id,
        page=query["page"],
        page_size=query["page_size"],
    )
    serialized = [
        {
            "id": str(p["id"]),
            "url": p["cloudinary_secure_url"],
            "filename": p["original_filename"],
            "uploaded_at": p["uploaded_at"].isoformat() if p.get("uploaded_at") else None,
        }
        for p in photos
    ]
    return paginated(serialized, query["page"], query["page_size"], total, data_key="photos")
