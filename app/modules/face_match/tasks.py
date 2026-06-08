"""
Celery tasks for async face matching.

Task 1: compute_photo_embeddings_task
  Triggered when a photographer uploads photos.
  Downloads the photo, runs InsightFace, stores embeddings in DB.

Task 2: face_match_task
  Triggered when a guest uploads a selfie.
  Queries pgvector for similar embeddings, saves results, updates job status.
"""
import json
import logging
import uuid
from datetime import datetime, timezone

import numpy as np
import requests

from app.config.settings import config

logger = logging.getLogger(__name__)


def get_celery():
    from app import celery_app
    return celery_app


# ─── Task 1: Pre-compute embeddings when photos are uploaded ─────────────────

def compute_photo_embeddings_task_fn(photo_id: str, photo_url: str) -> None:
    from app.extensions.database import get_db
    from app.modules.face_match.engine import get_all_face_embeddings
    from app.modules.photos.repository import insert_face_embeddings, update_embedding_status

    logger.info("Computing embeddings for photo %s", photo_id)
    try:
        update_embedding_status(photo_id, "processing")

        resp = requests.get(photo_url, timeout=30)
        resp.raise_for_status()
        embeddings = get_all_face_embeddings(resp.content)

        if not embeddings:
            logger.info("No faces detected in photo %s", photo_id)
            update_embedding_status(photo_id, "done")
            return

        insert_face_embeddings(photo_id, embeddings)
        update_embedding_status(photo_id, "done")
        logger.info("Stored %d embedding(s) for photo %s", len(embeddings), photo_id)
    except Exception as exc:
        logger.error("Embedding computation failed for photo %s: %s", photo_id, exc)
        update_embedding_status(photo_id, "failed")
        raise


# ─── Task 2: Match a selfie against event photo embeddings ───────────────────

def face_match_task_fn(job_id: str, event_id: str, selfie_bytes: bytes) -> None:
    from app.extensions.database import get_db
    from app.modules.face_match.engine import get_largest_face_embedding

    logger.info("Processing face match job %s for event %s", job_id, event_id)

    try:
        _update_job_status(job_id, "processing")

        selfie_emb = get_largest_face_embedding(selfie_bytes)
        if selfie_emb is None:
            _update_job_status(job_id, "failed", error="No face detected in selfie.")
            return

        vector_str = "[" + ",".join(f"{v:.6f}" for v in selfie_emb.tolist()) + "]"

        with get_db() as conn:
            with conn.cursor() as cur:
                # DISTINCT ON (p.id) returns the best (highest similarity) match per
                # photo, preventing the same photo from appearing multiple times in
                # results when it contains multiple faces that match.
                cur.execute(
                    """
                    SELECT DISTINCT ON (p.id)
                           p.id,
                           p.cloudinary_secure_url,
                           1 - (e.embedding <=> %s::vector) AS similarity
                    FROM photo_face_embeddings e
                    JOIN photos p ON p.id = e.photo_id
                    WHERE p.event_id = %s
                      AND 1 - (e.embedding <=> %s::vector) >= %s
                    ORDER BY p.id, similarity DESC
                    LIMIT 200
                    """,
                    (vector_str, event_id, vector_str, 1.0 - config.MATCH_DISTANCE_THRESHOLD),
                )
                matches = [
                    {
                        "photo_id": str(r["id"]),
                        "url": r["cloudinary_secure_url"],
                        "similarity": float(r["similarity"]),
                    }
                    for r in cur.fetchall()
                ]

        # Sort by similarity descending (DISTINCT ON order is by p.id)
        matches.sort(key=lambda x: x["similarity"], reverse=True)

        _update_job_status(job_id, "completed", result=matches)
        logger.info("Job %s completed — %d match(es) found.", job_id, len(matches))

    except Exception as exc:
        logger.exception("Face match job %s failed: %s", job_id, exc)
        _update_job_status(job_id, "failed", error="Processing failed. Please try again.")
        raise


def _update_job_status(job_id: str, status: str, result: list = None, error: str = None) -> None:
    from app.extensions.database import get_db
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE face_match_jobs
                SET status = %s,
                    result = %s,
                    error_message = %s,
                    updated_at = NOW(),
                    completed_at = CASE WHEN %s IN ('completed', 'failed') THEN NOW() ELSE NULL END
                WHERE id = %s
                """,
                (status, json.dumps(result) if result else None, error, status, job_id),
            )


# ─── Celery task wrappers ─────────────────────────────────────────────────────

try:
    from celery import shared_task

    @shared_task(bind=True, max_retries=3, default_retry_delay=60, queue="embeddings")
    def compute_photo_embeddings_task(self, photo_id: str, photo_url: str):
        try:
            compute_photo_embeddings_task_fn(photo_id, photo_url)
        except Exception as exc:
            raise self.retry(exc=exc)

    @shared_task(bind=True, max_retries=2, default_retry_delay=30, queue="face_match")
    def face_match_task(self, job_id: str, event_id: str, selfie_b64: str):
        import base64
        try:
            selfie_bytes = base64.b64decode(selfie_b64.encode("utf-8"))
            face_match_task_fn(job_id, event_id, selfie_bytes)
        except Exception as exc:
            raise self.retry(exc=exc)

except ImportError:
    logger.warning("Celery not available — async tasks will not function.")
    compute_photo_embeddings_task = None
    face_match_task = None
