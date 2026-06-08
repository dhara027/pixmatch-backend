"""
Events repository — all raw SQL for event operations.
Uses the shared connection pool context manager.
"""
import logging
from typing import Optional

from app.extensions.database import get_db

logger = logging.getLogger(__name__)


def create_event(
    photographer_id: str,
    photographer_name: str,
    event_name: str,
    event_location: str,
    event_date,
) -> dict:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO events
                    (photographer_id, photographer_name, event_name, event_location, event_date)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, photographer_id, photographer_name,
                          event_name, event_location, event_date, created_at
                """,
                (photographer_id, photographer_name, event_name, event_location, event_date),
            )
            return dict(cur.fetchone())


def get_event_by_id(event_id: str) -> Optional[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, photographer_id, photographer_name,
                       event_name, event_location, event_date, created_at, updated_at
                FROM events
                WHERE id = %s AND is_active = TRUE
                """,
                (event_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def list_events_by_photographer(
    photographer_id: str,
    page: int = 1,
    page_size: int = 10,
) -> tuple[list[dict], int]:
    offset = (page - 1) * page_size
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS total
                FROM events
                WHERE photographer_id = %s AND is_active = TRUE
                """,
                (photographer_id,),
            )
            total = cur.fetchone()["total"]

            cur.execute(
                """
                SELECT e.id, e.photographer_name, e.event_name, e.event_location,
                       e.event_date, e.created_at,
                       COALESCE(p.total_photos, 0) AS total_photos
                FROM events e
                LEFT JOIN event_photo_count p ON p.event_id = e.id
                WHERE e.photographer_id = %s AND e.is_active = TRUE
                ORDER BY e.created_at DESC
                LIMIT %s OFFSET %s
                """,
                (photographer_id, page_size, offset),
            )
            rows = [dict(r) for r in cur.fetchall()]
            return rows, total


def soft_delete_event(event_id: str, photographer_id: str) -> bool:
    """Only the owner can delete their own event."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE events SET is_active = FALSE, updated_at = NOW()
                WHERE id = %s AND photographer_id = %s AND is_active = TRUE
                """,
                (event_id, photographer_id),
            )
            return cur.rowcount > 0
