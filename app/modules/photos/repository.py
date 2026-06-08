"""
Photos repository — DB operations for photo metadata.
"""
import json
import logging

from psycopg2.extras import execute_values

from app.extensions.database import get_db

logger = logging.getLogger(__name__)


def insert_photo(
    event_id: str,
    cloudinary_public_id: str,
    cloudinary_secure_url: str,
    original_filename: str,
    file_size_bytes: int,
    mime_type: str,
) -> dict:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO photos
                    (event_id, cloudinary_public_id, cloudinary_secure_url,
                     original_filename, file_size_bytes, mime_type)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, event_id, cloudinary_public_id,
                          cloudinary_secure_url, original_filename, uploaded_at
                """,
                (event_id, cloudinary_public_id, cloudinary_secure_url,
                 original_filename, file_size_bytes, mime_type),
            )
            return dict(cur.fetchone())


def upsert_photo_count(event_id: str, increment: int = 1) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO event_photo_count (event_id, total_photos)
                VALUES (%s, %s)
                ON CONFLICT (event_id) DO UPDATE
                    SET total_photos = event_photo_count.total_photos + EXCLUDED.total_photos,
                        updated_at = NOW()
                """,
                (event_id, increment),
            )


def list_photos_by_event(event_id: str, page: int = 1, page_size: int = 20) -> tuple[list, int]:
    offset = (page - 1) * page_size
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total FROM photos WHERE event_id = %s", (event_id,))
            total = cur.fetchone()["total"]
            cur.execute(
                """
                SELECT id, cloudinary_public_id, cloudinary_secure_url,
                       original_filename, file_size_bytes, mime_type, uploaded_at
                FROM photos WHERE event_id = %s
                ORDER BY uploaded_at DESC
                LIMIT %s OFFSET %s
                """,
                (event_id, page_size, offset),
            )
            rows = [dict(r) for r in cur.fetchall()]
            return rows, total


def insert_face_embeddings(photo_id: str, embeddings: list[dict]) -> None:
    """Batch insert face embeddings for a photo (one row per detected face)."""
    if not embeddings:
        return

    rows = []
    for i, emb in enumerate(embeddings):
        vector_str = "[" + ",".join(f"{v:.6f}" for v in emb["embedding"]) + "]"
        bbox_json = json.dumps(emb.get("bbox", []))
        rows.append((photo_id, i, vector_str, bbox_json))

    with get_db() as conn:
        with conn.cursor() as cur:
            # execute_values sends all rows in a single round trip (one INSERT ... VALUES (...),(...),...)
            execute_values(
                cur,
                """
                INSERT INTO photo_face_embeddings (photo_id, face_index, embedding, bbox)
                VALUES %s
                ON CONFLICT DO NOTHING
                """,
                rows,
                template="(%s, %s, %s::vector, %s)",
            )


def update_embedding_status(photo_id: str, status: str) -> None:
    """Update the embedding_status column so monitoring/debugging reflects actual state."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE photos SET embedding_status = %s WHERE id = %s",
                (status, photo_id),
            )
