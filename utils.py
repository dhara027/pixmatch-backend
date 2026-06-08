import jwt
import bcrypt
import datetime
import random
import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from dotenv import load_dotenv
import re
 
load_dotenv()
 
# Password hashing
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
 
def check_password(password, hashed):
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
 
# JWT
def generate_jwt_token(user_id, email):
    payload = {'user_id': user_id, 'email': email,
               'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=15)}
    return jwt.encode(payload, os.getenv('JWT_SECRET'), algorithm='HS256')
 
def generate_refresh_token(user_id, email):
    payload = {'user_id': user_id, 'email': email,
               'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)}
    return jwt.encode(payload, os.getenv('JWT_REFRESH_SECRET'), algorithm='HS256')
 
def verify_jwt_token(token):
    try:
        return jwt.decode(token, os.getenv('JWT_SECRET'), algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
 
def verify_refresh_token(token):
    try:
        return jwt.decode(token, os.getenv('JWT_REFRESH_SECRET'), algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
 
# OTP
def generate_otp():
    return str(random.randint(100000, 999999))
 
# Send email
def send_email(to_email, subject, html_content):
    try:
        message = Mail(from_email=os.getenv('FROM_EMAIL'), to_emails=to_email,
                       subject=subject, html_content=html_content)
        sg = SendGridAPIClient(os.getenv('SENDGRID_API_KEY'))
        response = sg.send(message)
        return response.status_code == 202
    except Exception as e:
        print(f"Error sending email: {e}")
        return False
 
# Validation
def validate_email(email):
    return re.match(r"^[a-zA-Z0-9+_.-]+@[a-zA-Z0-9.-]+$", email)
 
def validate_mobile(mobile):
    return re.match(r"^[6-9]\d{9}$", mobile)
 
def validate_password(password):
    return re.match(r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[@$!%*#?&]).{6,}$", password)
 
 