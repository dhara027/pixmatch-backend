"""
File upload validation:
  - MIME type whitelist via magic byte detection (not Content-Type header)
  - File size limit (validated before full request body buffering via Content-Length)
  - HEIC brand code verification to reject video files (MP4/MOV share ftyp prefix)
"""
import io
import logging
from typing import BinaryIO

from flask import request as flask_request

from app.config.settings import config
from app.shared.exceptions import FileValidationError

logger = logging.getLogger(__name__)

# Valid HEIC brand codes (4-byte subtype after 'ftyp' atom) that confirm the
# file is actually a HEIF image, not MP4/MOV/M4V which share the ftyp prefix.
_HEIC_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"}


def _detect_mime(header: bytes) -> str | None:
    if header[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if header[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    # ISO Base Media File Format: find 'ftyp' within first 12 bytes and verify
    # the brand code is one of the known HEIC variants (not MP4/MOV).
    ftyp_pos = header.find(b"ftyp")
    if 0 <= ftyp_pos <= 8:
        brand = header[ftyp_pos + 4: ftyp_pos + 8]
        if brand in _HEIC_BRANDS:
            return "image/heic"
    return None


def validate_image_file(file: BinaryIO, filename: str = "") -> str:
    """
    Validate that `file` is an allowed image type within size limits.
    Returns the detected MIME type string.
    Raises FileValidationError on any violation.

    Size check uses Content-Length header first to reject oversized requests
    before the full body is buffered into memory.
    """
    # Early size rejection via Content-Length header (before reading the body)
    try:
        content_length = flask_request.content_length
        if content_length and content_length > config.CLOUDINARY_MAX_FILE_BYTES:
            max_mb = config.CLOUDINARY_MAX_FILE_BYTES / (1024 * 1024)
            raise FileValidationError(f"File exceeds maximum size of {max_mb:.0f} MB.")
    except RuntimeError:
        pass  # Not in a request context (e.g., tests)

    header = file.read(12)
    file.seek(0)

    if len(header) < 4:
        raise FileValidationError("File is too small to be a valid image.")

    detected_mime = _detect_mime(header)
    if not detected_mime:
        raise FileValidationError("File type not allowed. Accepted: JPEG, PNG, WebP, HEIC.")

    if detected_mime not in config.ALLOWED_IMAGE_MIMES:
        raise FileValidationError(f"File type '{detected_mime}' is not allowed.")

    # Accurate size check by seeking to end (body already buffered by Werkzeug)
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)

    if size > config.CLOUDINARY_MAX_FILE_BYTES:
        max_mb = config.CLOUDINARY_MAX_FILE_BYTES / (1024 * 1024)
        raise FileValidationError(f"File exceeds maximum size of {max_mb:.0f} MB.")

    return detected_mime
