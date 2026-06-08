import redis
import os
from dotenv import load_dotenv
 
load_dotenv()
 
redis_client = redis.StrictRedis(
    host=os.getenv('REDIS_HOST'),
    port=int(os.getenv('REDIS_PORT')),
    db=0,
    decode_responses=True
)
 
# Email OTP with attempt tracking
def set_otp(email, otp, expiry=300):
    redis_client.setex(f"otp:{email}", expiry, otp)
    redis_client.setex(f"otp_attempts:{email}", expiry, 3)
 
def get_otp(email):
    return redis_client.get(f"otp:{email}")
 
def decrease_otp_attempt(email):
    attempts = redis_client.decr(f"otp_attempts:{email}")
    return int(attempts)
 
def delete_otp(email):
    redis_client.delete(f"otp:{email}")
    redis_client.delete(f"otp_attempts:{email}")
 
# Password Reset Token
def set_reset_token(email, token, expiry=120):
    redis_client.setex(f"reset:{email}", expiry, token)
    redis_client.setex(f"reset_attempts:{email}", expiry, 3)
 
def get_reset_token(email):
    return redis_client.get(f"reset:{email}")
 
def decrease_reset_attempt(email):
    attempts = redis_client.decr(f"reset_attempts:{email}")
    return int(attempts)
 
def delete_reset_token(email):
    redis_client.delete(f"reset:{email}")
    redis_client.delete(f"reset_attempts:{email}")
 
# Refresh Token
def set_refresh_token(email, token, expiry=604800):  # 7 days
    redis_client.setex(f"refresh:{email}", expiry, token)
 
def get_refresh_token(email):
    return redis_client.get(f"refresh:{email}")
 
def delete_refresh_token(email):
    redis_client.delete(f"refresh:{email}")
 
 