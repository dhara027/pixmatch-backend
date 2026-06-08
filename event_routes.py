from flask import Blueprint, request, jsonify, send_file
from models import get_db_connection
import qrcode
import io

event_bp = Blueprint('event', __name__)

# ---------------- Create Event ----------------
@event_bp.route('/create', methods=['POST'])
def create_event():
    data = request.get_json()
    photographer_name = data.get('photographer_name')
    event_name = data.get('event_name')
    event_location = data.get('event_location')
    event_date = data.get('event_date')   # <-- event_date from request

    # Validate required fields
    if not all([photographer_name, event_name, event_location, event_date]):
        return jsonify({"error": "All fields (photographer_name, event_name, event_location, event_date) are required"}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Insert with event_date also
        cur.execute("""
            INSERT INTO events (photographer_name, event_name, event_location, event_date)
            VALUES (%s, %s, %s, %s)
            RETURNING uuid;
        """, (photographer_name, event_name, event_location, event_date))

        event_uuid = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        # Generate QR code using UUID
        qr_url = f"http://localhost:3000/upload-selfie/{event_uuid}"
        qr_img = qrcode.make(qr_url)

        # Convert QR to bytes for sending
        buf = io.BytesIO()
        qr_img.save(buf, format='PNG')
        buf.seek(0)

        # Send QR as downloadable file
        return send_file(
            buf,
            mimetype='image/png',
            as_attachment=True,
            download_name=f'event_{event_uuid}_qr.png'
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------- Get All Events ----------------
@event_bp.route('/list', methods=['GET'])
def list_events():
    try:
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 10))
        offset = (page - 1) * page_size

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM events WHERE is_deleted=FALSE AND is_active=TRUE")
        total_count = cur.fetchone()[0]

        # Fetch events with event_date also
        cur.execute("""
            SELECT uuid, photographer_name, event_name, event_location, event_date, created_at, updated_at
            FROM events
            WHERE is_deleted = FALSE AND is_active = TRUE
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (page_size, offset))

        events = cur.fetchall()
        cur.close()
        conn.close()

        events_list = []
        for e in events:
            event_uuid, photographer_name, event_name, event_location, event_date, created_at, updated_at = e
            events_list.append({
                "uuid": event_uuid,
                "photographer_name": photographer_name,
                "event_name": event_name,
                "event_location": event_location,
                "event_date": str(event_date),  # convert date to string for JSON
                "created_at": created_at,
                "updated_at": updated_at
            })

        return jsonify({
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": (total_count + page_size - 1) // page_size,
            "events": events_list
        }), 200

    except Exception as ex:
        return jsonify({"error": str(ex)}), 500




        # ---------------- Get Event by UUID ----------------
@event_bp.route('/get/<uuid>', methods=['GET'])
def get_event_by_uuid(uuid):
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Fetch event by UUID
        cur.execute("""
            SELECT uuid, photographer_name, event_name, event_location, event_date, created_at, updated_at
            FROM events
            WHERE uuid = %s AND is_deleted = FALSE AND is_active = TRUE
        """, (uuid,))

        event = cur.fetchone()
        cur.close()
        conn.close()

        if not event:
            return jsonify({"message": "Event not found"}), 404

        event_uuid, photographer_name, event_name, event_location, event_date, created_at, updated_at = event

        return jsonify({
            "uuid": event_uuid,
            "photographer_name": photographer_name,
            "event_name": event_name,
            "event_location": event_location,
            "event_date": str(event_date),
            "created_at": created_at,
            "updated_at": updated_at
        }), 200

    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

