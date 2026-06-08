from flask import Blueprint, request, jsonify
from models import get_db_connection
import redis_service
from utils import (hash_password, check_password, generate_jwt_token, generate_refresh_token,
                   generate_otp, send_email, validate_email, validate_mobile, validate_password, verify_refresh_token)
from redis_service import (set_otp, get_otp, decrease_otp_attempt, delete_otp,
                           set_reset_token, get_reset_token, decrease_reset_attempt, delete_reset_token,
                           set_refresh_token, get_refresh_token, delete_refresh_token)
import datetime
 
auth_bp = Blueprint('auth', __name__)
 
# ----------------- Signup -----------------
@auth_bp.route('/signup', methods=['POST'])
def signup():
    try:
        data = request.get_json()
        email = data.get('email')
        mobile_no = data.get('mobile_no')
        password = data.get('password')
        confirmpassword = data.get('confirmpassword')
 
        if not all([email, mobile_no, password, confirmpassword]):
            return jsonify({'error': 'All fields are required'}), 400
 
        if not validate_email(email):
            return jsonify({'error':'Invalid email format'}), 400
        if not validate_mobile(mobile_no):
            return jsonify({'error':'Invalid mobile number'}), 400
        if not validate_password(password):
            return jsonify({'error':'Weak password'}), 400
 
        if password != confirmpassword:
            return jsonify({'error': 'Passwords do not match'}), 400
 
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Check email
                cur.execute('SELECT id FROM users WHERE email=%s', (email,))
                if cur.fetchone():
                    return jsonify({'error': 'Email already exists'}), 409
 
                # Check mobile number
                cur.execute('SELECT id FROM users WHERE mobile_no=%s', (mobile_no,))
                if cur.fetchone():
                    return jsonify({'error': 'Mobile number already exists'}), 409
 
                hashed_password = hash_password(password)
                cur.execute('INSERT INTO users (email, mobile_no, password) VALUES (%s,%s,%s) RETURNING id',
                            (email, mobile_no, hashed_password))
                user_id = cur.fetchone()[0]
                conn.commit()
 
        otp = generate_otp()
        set_otp(email, otp, expiry=120)
        send_email(email, "Verify Your Email", f"<h2>Email Verification</h2><p>OTP: <strong>{otp}</strong></p>")
 
        return jsonify({'message':'Registration successfully! Please check your email for the OTP verify.'}), 201
 
    except Exception as e:
        return jsonify({'error': str(e)}), 500
 
 
# ----------------- Verify OTP -----------------
@auth_bp.route('/verify-otp', methods=['POST'])
def verify_otp_route():
    try:
        data = request.get_json()
        email = data.get('email')
        otp = data.get('otp')
 
        if not all([email, otp]):
            return jsonify({'error':'Email and OTP required'}),400
 
        stored_otp = get_otp(email)
        if not stored_otp:
            return jsonify({'error':'OTP expired or not found'}),400
        if stored_otp != otp:
            attempts_left = decrease_otp_attempt(email)
            if attempts_left <= 0:
                delete_otp(email)
                return jsonify({'error':'OTP invalid. Please request a new one.'}),400
            return jsonify({'error':f'Invalid OTP. Attempts left: {attempts_left}'}),400
 
        delete_otp(email)
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('UPDATE users SET is_email_verified =TRUE WHERE email=%s', (email,))
                conn.commit()
 
        return jsonify({'message':'Email verified successfully'}),200
 
    except Exception as e:
        return jsonify({'error': str(e)}), 500
 
# ----------------- Login -----------------
@auth_bp.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')

        if not all([email, password]):
            return jsonify({'error':'Email and password required'}),400

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT id,password,is_email_verified FROM users WHERE email=%s', (email,))
                user = cur.fetchone()
                if not user:
                    return jsonify({'error':'Invalid credentials'}),401
                user_id, hashed_password, is_email_verified = user

                if not check_password(password, hashed_password):
                    return jsonify({'error':'Invalid credentials'}),401

                if not is_email_verified:
                    return jsonify({'error':'Email not verified'}),401

                token = generate_jwt_token(user_id,email)
                refresh_token = generate_refresh_token(user_id,email)
                set_refresh_token(email,refresh_token)

                cur.execute('UPDATE users SET last_login=%s WHERE id=%s',
                            (datetime.datetime.now(),user_id))
                conn.commit()

        return jsonify({
            'message': 'Login successful',
            'token': token,
            'refresh_token': refresh_token,
            'user': {
                'id': user_id,
                'email': email
            }
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}),500

 
 
# ----------------- Refresh Token -----------------
@auth_bp.route('/refresh-token', methods=['POST'])
def refresh_token_route():
    try:
        data = request.get_json()
        refresh_token = data.get('refresh_token')
        if not refresh_token:
            return jsonify({'error':'Refresh token required'}),400
 
        payload = None
        for email in [k.decode() for k in redis_service.redis_client.keys("refresh:*")]:
            if get_refresh_token(email.split("refresh:")[1]) == refresh_token:
                payload = verify_refresh_token(refresh_token)
                break
        if not payload:
            return jsonify({'error':'Invalid refresh token'}),401
 
        new_token = generate_jwt_token(payload['user_id'], payload['email'])
        return jsonify({'token': new_token}),200
 
    except Exception as e:
        return jsonify({'error': str(e)}),500
 
 
# ----------------- Forgot Password with Link -----------------
@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    try:
        data = request.get_json()
        email = data.get('email')
        if not email:
            return jsonify({'error': 'Email required'}), 400
 
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT id FROM users WHERE email=%s', (email,))
                user = cur.fetchone()
                if not user:
                    return jsonify({'message': 'If email exists, reset link sent'}), 200
 
        # generate token
        import uuid
        reset_token = str(uuid.uuid4())
 
        # save in redis with expiry (15 min)
        set_reset_token(email, reset_token, expiry=900)
 
        # create reset link (frontend page URL)
        reset_link = (
    f"http://localhost:8080/reset-password?"
    f"email={email}&token={reset_token}"
)

 
        # send email with link
        send_email(
            email,
            "Password Reset Link",
            f"<h2>Password Reset</h2><p>Click the link below to reset your password:</p><a href='{reset_link}'>{reset_link}</a>"
        )
 
        return jsonify({'message': 'password reset link has been sent. Please check your Email'}), 200
 
    except Exception as e:
        return jsonify({'error': str(e)}), 500
 
 
# ----------------- Reset Password -----------------
@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    try:
        data = request.get_json()
        email = data.get('email')
        token = data.get('token')
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')
 
        # 1. Validate input
        if not all([email, token, new_password, confirm_password]):
            return jsonify({'error': 'All fields required'}), 400
        if new_password != confirm_password:
            return jsonify({'error': 'Passwords do not match'}), 400
        if not validate_password(new_password):
            return jsonify({'error': 'Weak password'}), 400
 
        # 2. Fetch stored token from Redis
        stored_token = get_reset_token(email)
        if not stored_token or stored_token != token:
            return jsonify({'error': 'Invalid or expired reset token. Please request a new one'}), 400
 
        # 3. Delete token after successful verification (one-time use)
        delete_reset_token(email)
 
        # 4. Hash new password
        hashed_password = hash_password(new_password)
 
        # 5. Update password in DB
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'UPDATE users SET password=%s WHERE email=%s',
                    (hashed_password, email)
                )
                conn.commit()
 
        return jsonify({'message': 'Password reset successfully'}), 200
 
    except Exception as e:
        return jsonify({'error': str(e)}), 500
 
 