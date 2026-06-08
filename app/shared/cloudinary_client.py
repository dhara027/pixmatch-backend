"""
Centralized Cloudinary service.
Configured once; provides typed upload helpers with optimization.
"""
import logging
import re
from typing import Any

import cloudinary
import cloudinary.uploader

from app.config.settings import config
from app.shared.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)


def init_cloudinary() -> None:
    cloudinary.config(
        cloud_name=config.CLOUDINARY_CLOUD_NAME,
        api_key=config.CLOUDINARY_API_KEY,
        api_secret=config.CLOUDINARY_API_SECRET,
        secure=True,
    )
    logger.info("Cloudinary initialized (cloud_name=%s)", config.CLOUDINARY_CLOUD_NAME)


def upload_event_photo(
    file_data,
    event_id: str,
    photographer_id: str,
    event_name: str = "",
) -> dict[str, Any]:
    """
    Upload a photographer's event photo to Cloudinary with optimization.
    Folder is named after the event (sanitized) for easy Cloudinary navigation.
    Returns the Cloudinary response dict.
    """
    safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", event_name).strip("_")[:60] if event_name else event_id
    folder = f"pixmatch_events/{safe_name}"

    try:
        result = cloudinary.uploader.upload(
            file_data,
            folder=folder,
            resource_type="image",
            allowed_formats=["jpg", "jpeg", "png", "webp", "heic"],
            max_bytes=config.CLOUDINARY_MAX_FILE_BYTES,
            transformation=[
                {"width": 2048, "height": 2048, "crop": "limit"},
                {"quality": "auto:good"},
                {"fetch_format": "auto"},
            ],
            tags=[f"event:{event_id}", f"photographer:{photographer_id}"],
            context=f"event_id={event_id}|photographer_id={photographer_id}",
            overwrite=False,
            unique_filename=True,
        )
        return result
    except Exception as exc:
        logger.error("Cloudinary upload failed for event %s: %s", event_id, exc)
        raise ExternalServiceError("Photo upload service temporarily unavailable.") from exc
