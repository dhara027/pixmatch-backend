# face_match_insightface.py
import os
import io
import tempfile
import zipfile
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

from flask import Blueprint, request, jsonify, send_file
import requests
from PIL import Image
import numpy as np

# HEIC support for PIL
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except Exception:
    pass

# cloudinary
import cloudinary
import cloudinary.api
from dotenv import load_dotenv

# InsightFace
from insightface.app import FaceAnalysis

load_dotenv()

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

face_match_bp = Blueprint("face_match", __name__)

# ------------------------------------------------
# Config
# ------------------------------------------------
INSIGHTFACE_CTX_ID = int(os.getenv("INSIGHTFACE_CTX_ID", "0"))
DET_SIZE = (1024, 1024)  # better for angle + small face
MATCH_DISTANCE_THRESHOLD = float(os.getenv("MATCH_DISTANCE_THRESHOLD", "0.50"))  # improved accuracy
MAX_DOWNLOAD_WORKERS = int(os.getenv("MAX_DOWNLOAD_WORKERS", "8"))
EVENT_EMBED_CACHE_SIZE = int(os.getenv("EVENT_EMBED_CACHE_SIZE", "1024"))

# ------------------------------------------------
# Initialize InsightFace (heavy)
# ------------------------------------------------
print("Preparing InsightFace models (this may take a few seconds)...")
fa = FaceAnalysis(allowed_modules=["detection", "recognition"])
fa.prepare(ctx_id=INSIGHTFACE_CTX_ID, det_size=DET_SIZE)
print("InsightFace ready. ctx_id=", INSIGHTFACE_CTX_ID)


# ------------------------------------------------
# Utilities
# ------------------------------------------------
def to_rgb_pil(path_or_bytes):
    if isinstance(path_or_bytes, (bytes, bytearray)):
        img = Image.open(io.BytesIO(path_or_bytes))
    else:
        img = Image.open(path_or_bytes)
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


def pil_to_numpy(img_pil):
    arr = np.asarray(img_pil)
    arr = arr[:, :, ::-1].copy()  # RGB → BGR
    return arr


def cosine_distance(a: np.ndarray, b: np.ndarray):
    a = a.astype(np.float32)
    b = b.astype(np.float32)
    an = a / (np.linalg.norm(a) + 1e-10)
    bn = b / (np.linalg.norm(b) + 1e-10)
    sim = np.dot(an, bn)
    return 1.0 - float(sim)


@lru_cache(maxsize=EVENT_EMBED_CACHE_SIZE)
def cached_event_embeddings(url: str):
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        img_pil = to_rgb_pil(resp.content)
        arr = pil_to_numpy(img_pil)
        faces = fa.get(arr)
        out = []
        for f in faces:
            if hasattr(f, "embedding") and f.embedding is not None:
                out.append({
                    "embedding": np.array(f.embedding, dtype=np.float32),
                    "bbox": getattr(f, "bbox", None)
                })
        return out
    except Exception as e:
        print(f"[cached_event_embeddings] failed for url {url}: {e}")
        return []


# ------------------------------------------------
# API endpoint: upload selfie and match
# ------------------------------------------------
@face_match_bp.route("/upload-selfie", methods=["POST"])
def upload_selfie():
    event_uuid = request.form.get("event_uuid")
    file = request.files.get("file")

    if not event_uuid or not file:
        return jsonify({"error": "Event UUID and selfie file are required"}), 400

    try:
        selfie_bytes = file.read()
        selfie_pil = to_rgb_pil(selfie_bytes)
        selfie_arr = pil_to_numpy(selfie_pil)

        # detect all possible faces (not only 1)
        selfie_faces = fa.get(selfie_arr)
        if not selfie_faces:
            return jsonify({"error": "No face detected in selfie"}), 400

        # pick largest + stable embedding average for extreme accuracy
        selfie_faces = sorted(selfie_faces,
                              key=lambda x: (x.bbox[2]-x.bbox[0]) * (x.bbox[3]-x.bbox[1]),
                              reverse=True)
        all_embs = [np.array(f.embedding, dtype=np.float32) for f in selfie_faces if f.embedding is not None]
        selfie_emb = np.mean(all_embs, axis=0).astype(np.float32)

        matched_photos = []
        cursor = None
        max_total = 500
        fetched = 0

        while True:
            params = {
                "type": "upload",
                "prefix": f"events/{event_uuid}",
                "max_results": 100
            }
            if cursor:
                params["next_cursor"] = cursor

            res = cloudinary.api.resources(**params)
            resources = res.get("resources", [])
            if not resources:
                break

            urls = [r.get("secure_url") for r in resources if r.get("secure_url")]
            fetched += len(urls)

            with ThreadPoolExecutor(max_workers=MAX_DOWNLOAD_WORKERS) as ex:
                future_to_url = {ex.submit(cached_event_embeddings, url): url for url in urls}
                for fut in as_completed(future_to_url):
                    url = future_to_url[fut]
                    try:
                        face_list = fut.result()
                        for face in face_list:
                            dist = cosine_distance(selfie_emb, face["embedding"])
                            if dist < MATCH_DISTANCE_THRESHOLD:
                                matched_photos.append(url)
                                break
                    except Exception as e:
                        print(f"[match loop] {url} failed: {e}")
                        continue

            cursor = res.get("next_cursor")
            if not cursor or fetched >= max_total:
                break

        if not matched_photos:
            return jsonify({"message": "No match found"}), 404

        encoded_urls = urllib.parse.quote(",".join(matched_photos))
        return jsonify({
            "message": "Match found!",
            "matched_photos": matched_photos,
            "download_zip_url": f"/api/face/download-matched-photos?urls={encoded_urls}"
        }), 200

    except Exception as e:
        print("upload_selfie error:", e)
        return jsonify({"error": str(e)}), 500


# ------------------------------------------------
# Download endpoint
# ------------------------------------------------
@face_match_bp.route("/download-matched-photos", methods=["GET"])
def download_matched_photos():
    urls = request.args.get("urls")
    if not urls:
        return jsonify({"error": "No photo URLs provided"}), 400

    urls = urllib.parse.unquote(urls).split(",")

    if len(urls) == 1:
        url = urls[0]
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            with open(temp_file.name, "wb") as f:
                f.write(resp.content)
            return send_file(temp_file.name, as_attachment=True, download_name="photo.jpg", mimetype="image/jpeg")
        else:
            return jsonify({"error": "Unable to download the image"}), 500

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for idx, url in enumerate(urls, start=1):
            try:
                resp = requests.get(url, timeout=15)
                if resp.status_code == 200:
                    zipf.writestr(f"photo_{idx}.jpg", resp.content)
            except Exception as e:
                print(f"Error downloading {url}: {e}")

    zip_buffer.seek(0)
    return send_file(zip_buffer, as_attachment=True, download_name="matched_photos.zip", mimetype="application/zip")
