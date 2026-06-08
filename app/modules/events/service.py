"""
Events service — QR generation and business rules.
"""
import io
import logging

import qrcode
from flask import current_app

from app.config.settings import config
from app.modules.events import repository as repo
from app.shared.exceptions import AuthorizationError, NotFoundError

logger = logging.getLogger(__name__)


def _serialize_event(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "photographer_name": row["photographer_name"],
        "event_name": row["event_name"],
        "event_location": row["event_location"],
        "event_date": str(row["event_date"]),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
        "total_photos": row.get("total_photos", 0),
    }


class EventService:

    def create_event(
        self,
        photographer_id: str,
        photographer_name: str,
        event_name: str,
        event_location: str,
        event_date,
    ) -> tuple[dict, bytes]:
        event = repo.create_event(
            photographer_id=photographer_id,
            photographer_name=photographer_name.strip(),
            event_name=event_name.strip(),
            event_location=event_location.strip(),
            event_date=event_date,
        )
        event_id = str(event["id"])
        # Build guest URL pointing to actual frontend (env-configured)
        guest_url = f"{config.FRONTEND_URL}/guest/{event_id}"
        qr_bytes = self._generate_qr_png(guest_url)
        logger.info("Event %s created by photographer %s.", event_id, photographer_id)
        return _serialize_event(event), qr_bytes

    def _generate_qr_png(self, url: str) -> bytes:
        img = qrcode.make(url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf.read()

    def generate_qr_for_event(self, event_id: str) -> bytes:
        """Public helper used by the QR download endpoint."""
        guest_url = f"{config.FRONTEND_URL}/guest/{event_id}"
        return self._generate_qr_png(guest_url)

    def get_event(self, event_id: str, photographer_id: str) -> dict:
        event = repo.get_event_by_id(event_id)
        if not event:
            raise NotFoundError("Event not found.")
        if str(event["photographer_id"]) != photographer_id:
            raise AuthorizationError("You do not have access to this event.")
        return _serialize_event(event)

    def get_event_public(self, event_id: str) -> dict:
        """Public read for QR scan — no auth required, returns limited fields."""
        event = repo.get_event_by_id(event_id)
        if not event:
            raise NotFoundError("Event not found.")
        return {
            "id": str(event["id"]),
            "event_name": event["event_name"],
            "event_location": event["event_location"],
            "event_date": str(event["event_date"]),
        }

    def list_events(self, photographer_id: str, page: int, page_size: int) -> tuple[list, int]:
        rows, total = repo.list_events_by_photographer(photographer_id, page, page_size)
        return [_serialize_event(r) for r in rows], total

    def delete_event(self, event_id: str, photographer_id: str) -> None:
        deleted = repo.soft_delete_event(event_id, photographer_id)
        if not deleted:
            raise NotFoundError("Event not found or you do not have permission to delete it.")


event_service = EventService()
