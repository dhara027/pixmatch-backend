"""
Photos service — upload orchestration with validation, Cloudinary, and DB metadata.
"""
import logging
from typing import BinaryIO

from app.modules.events.repository import get_event_by_id
from app.modules.photos import repository as photo_repo
from app.shared.cloudinary_client import upload_event_photo
from app.shared.exceptions import AuthorizationError, NotFoundError
from app.utils.file_validator import validate_image_file

logger = logging.getLogger(__name__)


class PhotoService:

    def upload_event_photos(
        self,
        event_id: str,
        photographer_id: str,
        files: list,
    ) -> dict:
        event = get_event_by_id(event_id)
        if not event:
            raise NotFoundError("Event not found.")
        if str(event["photographer_id"]) != photographer_id:
            raise AuthorizationError("You do not have permission to upload to this event.")

        uploaded = []
        errors = []

        for file in files:
            filename = file.filename or "unknown"
            try:
                mime = validate_image_file(file, filename)
                file.seek(0)

                result = upload_event_photo(
                    file_data=file,
                    event_id=event_id,
                    photographer_id=photographer_id,
                    event_name=str(event.get("event_name", "")),
                )

                photo_record = photo_repo.insert_photo(
                    event_id=event_id,
                    cloudinary_public_id=result["public_id"],
                    cloudinary_secure_url=result["secure_url"],
                    original_filename=filename,
                    file_size_bytes=result.get("bytes", 0),
                    mime_type=mime,
                )

                uploaded.append({
                    "id": str(photo_record["id"]),
                    "url": result["secure_url"],
                    "filename": filename,
                })

                try:
                    from app.config.settings import config as _cfg
                    from app.modules.face_match.tasks import (
                        compute_photo_embeddings_task,
                        compute_photo_embeddings_task_fn,
                    )
                    _pid = str(photo_record["id"])
                    _url = result["secure_url"]
                    if compute_photo_embeddings_task and _cfg.FLASK_ENV == "production":
                        compute_photo_embeddings_task.delay(photo_id=_pid, photo_url=_url)
                    else:
                        import threading
                        threading.Thread(
                            target=compute_photo_embeddings_task_fn,
                            args=(_pid, _url),
                            daemon=True,
                        ).start()
                except Exception as celery_exc:
                    logger.warning(
                        "Could not queue embedding task for photo %s: %s",
                        str(photo_record["id"]), celery_exc,
                    )

            except Exception as exc:
                # Log full detail server-side; return only a safe user-facing message
                logger.error("UPLOAD FAILED for file '%s': %s", filename, exc, exc_info=True)
                errors.append({"filename": filename, "error": "Upload failed. Please check the file and try again."})

        if uploaded:
            photo_repo.upsert_photo_count(event_id, len(uploaded))

        return {
            "uploaded_count": len(uploaded),
            "error_count": len(errors),
            "uploaded": uploaded,
            "errors": errors,
        }

    def list_photos(self, event_id: str, photographer_id: str, page: int, page_size: int) -> tuple:
        event = get_event_by_id(event_id)
        if not event:
            raise NotFoundError("Event not found.")
        if str(event["photographer_id"]) != photographer_id:
            raise AuthorizationError("You do not have access to this event.")
        return photo_repo.list_photos_by_event(event_id, page, page_size)


photo_service = PhotoService()
