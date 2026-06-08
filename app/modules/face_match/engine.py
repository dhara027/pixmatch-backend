"""
InsightFace engine — thread-safe lazy-loaded singleton.
CPU mode by default (ctx_id=-1), GPU via INSIGHTFACE_CTX_ID env var.
"""
import logging
import threading
from typing import Optional

import numpy as np
from PIL import Image
import io

logger = logging.getLogger(__name__)

_fa = None
_fa_lock = threading.Lock()


def get_face_app():
    global _fa
    # Double-checked locking: avoids acquiring the lock on every call after initialization.
    if _fa is None:
        with _fa_lock:
            if _fa is None:
                from app.config.settings import config
                from insightface.app import FaceAnalysis
                logger.info("Loading InsightFace models (this takes ~30s on first startup)...")
                fa = FaceAnalysis(allowed_modules=["detection", "recognition"])
                fa.prepare(ctx_id=config.INSIGHTFACE_CTX_ID, det_size=config.INSIGHTFACE_DET_SIZE)
                _fa = fa
                logger.info("InsightFace ready (ctx_id=%d).", config.INSIGHTFACE_CTX_ID)
    return _fa


def bytes_to_bgr(image_bytes: bytes) -> np.ndarray:
    """Convert raw image bytes to BGR numpy array for InsightFace.
    Applies EXIF rotation so mobile portrait photos are upright before detection.
    """
    from PIL import ImageOps
    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")
    arr = np.asarray(img)
    return arr[:, :, ::-1].copy()  # RGB → BGR


def get_largest_face_embedding(image_bytes: bytes) -> Optional[np.ndarray]:
    """
    Detect faces in image, return the embedding of the largest face.
    Returns None if no face detected.
    """
    fa = get_face_app()
    arr = bytes_to_bgr(image_bytes)
    faces = fa.get(arr)

    if not faces:
        return None

    largest = max(
        faces,
        key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])
    )

    if largest.embedding is None:
        return None

    emb = np.array(largest.embedding, dtype=np.float32)
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
    return emb


def get_all_face_embeddings(image_bytes: bytes) -> list[dict]:
    """
    Detect all faces, return list of {embedding, bbox} for storage.
    Used when processing event photos.
    """
    fa = get_face_app()
    arr = bytes_to_bgr(image_bytes)
    faces = fa.get(arr)

    result = []
    for face in faces:
        if face.embedding is None:
            continue
        emb = np.array(face.embedding, dtype=np.float32)
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm
        result.append({
            "embedding": emb.tolist(),
            "bbox": face.bbox.tolist() if face.bbox is not None else [],
        })
    return result
