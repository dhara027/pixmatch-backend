from flask import Blueprint, request, jsonify
from models import get_db_connection
import cloudinary
import cloudinary.uploader
import os
from dotenv import load_dotenv
from datetime import datetime
 
load_dotenv()
 
# Cloudinary config
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)
 
photo_bp = Blueprint('photo', __name__)
 
@photo_bp.route('/upload-event-photos', methods=['POST'])
def upload_event_photos():
    """
    Photographer uploads multiple photos for an event.
    Request Form:
        - event_uuid (str)
        - files[] (multiple images)
    """
    event_uuid = request.form.get('event_uuid')
    files = request.files.getlist('files')
 
    if not event_uuid or not files:
        return jsonify({"error": "Event UUID and files are required"}), 400
 
    uploaded_count = 0
 
    try:
        # Upload each photo to Cloudinary
        for file in files:
            cloudinary.uploader.upload(file, folder=f"events/{event_uuid}")
            uploaded_count += 1
 
        # Update event_photo_count table
        conn = get_db_connection()
        cur = conn.cursor()
 
        # Check if record exists
        cur.execute("SELECT total_photos FROM event_photo_count WHERE event_uuid=%s", (event_uuid,))
        row = cur.fetchone()
        if row:
            # Update existing total_photos
            new_total = row[0] + uploaded_count
            cur.execute("""
                UPDATE event_photo_count
                SET total_photos=%s, updated_at=%s
                WHERE event_uuid=%s
            """, (new_total, datetime.now(), event_uuid))
        else:
            # Insert new record
            cur.execute("""
                INSERT INTO event_photo_count (event_uuid, total_photos)
                VALUES (%s, %s)
            """, (event_uuid, uploaded_count))
 
        conn.commit()
        cur.close()
        conn.close()
 
        return jsonify({
            "message": f"{uploaded_count} photos uploaded successfully",
            "event_uuid": event_uuid,
            "total_photos": row[0] + uploaded_count if row else uploaded_count
        }), 201
 
    except Exception as e:
        return jsonify({"error": str(e)}), 500
 
 