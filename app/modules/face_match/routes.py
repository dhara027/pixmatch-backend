"""
Face match routes — /api/v1/face-match/*

POST /api/v1/face-match/jobs          → Upload selfie, create async job, return job_id
GET  /api/v1/face-match/jobs/<job_id> → Poll job status (requires job ownership token)
GET  /api/v1/face-match/download      → SSRF-protected parallel photo download
"""
import base64
import io
import json
import logging
import secrets
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import unquote

import requests
from flask import Blueprint, g, jsonify, request, send_file

from app.extensions.limiter_ext import limiter
from app.middleware.auth import optional_auth
from app.modules.face_match.tasks import face_match_task, face_match_task_fn
from app.shared.exceptions import FileValidationError, ValidationError
from app.utils.file_validator import validate_image_file
from app.utils.response import created, error, success
from app.utils.security import is_safe_cloudinary_url
from app.extensions.database import get_db

logger = logging.getLogger(__name__)

face_match_bp = Blueprint("face_match", __name__)

_MAX_DOWNLOAD_URLS = 20      # per-request URL cap (was 200 — DoS vector)
_DOWNLOAD_TIMEOUT = 10       # seconds per URL
_DOWNLOAD_WORKERS = 8        # parallel download threads


@face_match_bp.route("/jobs", methods=["POST"])
@optional_auth
def create_match_job():
    """
    Accept guest selfie upload.
    Creates a DB job record, dispatches Celery task, returns job ID immediately.
    Rate limited to 10 jobs per hour per IP to prevent resource exhaustion.
    """
    # Rate limit applied here (not at blueprint level) because this endpoint is
    # much more expensive than the rest (runs InsightFace).
    if limiter:
        limiter.limit("10 per hour")(lambda: None)()

    event_id = request.form.get("event_id", "").strip()
    file = request.files.get("file")

    if not event_id:
        return error("event_id is required.", code="VALIDATION_ERROR")
    if not file:
        return error("selfie file is required.", code="VALIDATION_ERROR")

    try:
        validate_image_file(file, file.filename or "")
        file.seek(0)
    except FileValidationError as exc:
        return error(str(exc), code="INVALID_FILE", status=400)

    selfie_bytes = file.read()
    job_id = str(uuid.uuid4())

    # job_token is returned to the client and required to poll this specific job.
    # Guests are anonymous so we cannot use user_id; a secret token prevents
    # arbitrary polling of other users' job results.
    job_token = secrets.token_urlsafe(32)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO face_match_jobs (id, event_id, status, job_token)
                VALUES (%s, %s, 'queued', %s)
                """,
                (job_id, event_id, job_token),
            )

    selfie_b64 = base64.b64encode(selfie_bytes).decode("utf-8")

    from app.config.settings import config as _cfg
    if face_match_task and _cfg.FLASK_ENV == "production":
        face_match_task.delay(job_id, event_id, selfie_b64)
    else:
        import threading
        threading.Thread(
            target=face_match_task_fn,
            args=(job_id, event_id, selfie_bytes),
            daemon=True,
        ).start()

    return created({
        "job_id": job_id,
        "job_token": job_token,
        "status": "queued",
        "poll_url": f"/api/v1/face-match/jobs/{job_id}",
    })


@face_match_bp.route("/jobs/<job_id>", methods=["GET"])
def get_job_status(job_id: str):
    """
    Poll for job completion.
    Requires job_token query parameter (returned on job creation) for ownership verification.
    """
    job_token = request.args.get("job_token", "").strip()
    if not job_token:
        return error("job_token query parameter is required.", code="AUTHENTICATION_REQUIRED", status=401)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, status, result, error_message, job_token,
                       created_at, completed_at
                FROM face_match_jobs WHERE id = %s
                """,
                (job_id,),
            )
            row = cur.fetchone()

    if not row:
        return error("Job not found.", code="NOT_FOUND", status=404)

    # Constant-time comparison to prevent timing oracle on job_token
    import hmac as _hmac
    if not _hmac.compare_digest(row["job_token"] or "", job_token):
        return error("Invalid job token.", code="FORBIDDEN", status=403)

    data = {
        "job_id": str(row["id"]),
        "status": row["status"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
    }

    if row["status"] == "completed":
        result = row["result"]
        if isinstance(result, str):
            result = json.loads(result)
        data["matched_photos"] = result or []

    if row["status"] == "failed":
        data["error"] = row["error_message"]

    return success(data)


@face_match_bp.route("/download", methods=["GET"])
@optional_auth
def download_photos():
    """
    SSRF-protected parallel photo download.
    Only accepts URLs from this application's Cloudinary account (validated by cloud name).
    Downloads happen in parallel (up to _DOWNLOAD_WORKERS concurrent fetches).
    """
    raw_urls = request.args.get("urls", "")
    if not raw_urls:
        return error("urls parameter is required.", code="VALIDATION_ERROR")

    urls = [u.strip() for u in unquote(raw_urls).split(",") if u.strip()]
    if not urls:
        return error("No valid URLs provided.", code="VALIDATION_ERROR")
    if len(urls) > _MAX_DOWNLOAD_URLS:
        return error(f"Maximum {_MAX_DOWNLOAD_URLS} URLs per download.", code="VALIDATION_ERROR")

    for url in urls:
        if not is_safe_cloudinary_url(url):
            logger.warning("SSRF attempt blocked: %s", url)
            return error("One or more URLs are not from the allowed domain.", code="INVALID_URL", status=400)

    def _fetch(url: str, idx: int) -> tuple[int, bytes | None]:
        try:
            resp = requests.get(url, timeout=_DOWNLOAD_TIMEOUT)
            if resp.status_code == 200:
                return idx, resp.content
        except Exception as exc:
            logger.warning("Failed to download %s: %s", url, exc)
        return idx, None

    if len(urls) == 1:
        _, content = _fetch(urls[0], 0)
        if not content:
            return error("Failed to download photo.", code="DOWNLOAD_FAILED", status=502)
        return send_file(
            io.BytesIO(content),
            mimetype="image/jpeg",
            as_attachment=True,
            download_name="photo.jpg",
        )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        with ThreadPoolExecutor(max_workers=_DOWNLOAD_WORKERS) as pool:
            futures = {pool.submit(_fetch, url, idx): idx for idx, url in enumerate(urls, 1)}
            for future in as_completed(futures):
                idx, content = future.result()
                if content:
                    zf.writestr(f"photo_{idx:04d}.jpg", content)

    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name="matched_photos.zip",
    )
