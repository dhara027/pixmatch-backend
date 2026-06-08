import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv
from datetime import datetime
 
load_dotenv()
 
def get_db_connection():
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST'),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        port=os.getenv('DB_PORT')
    )
    return conn
 
def init_db():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
 
            # Users table
            cur.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(100) UNIQUE NOT NULL,
                    mobile_no VARCHAR(15) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    is_email_verified BOOLEAN DEFAULT FALSE,
                    last_login TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    uuid VARCHAR(36) DEFAULT gen_random_uuid(),
                    is_deleted BOOLEAN DEFAULT FALSE,
                    is_active BOOLEAN DEFAULT TRUE
                )
            ''')
 
 
            # Events table
 
            cur.execute('''
                CREATE TABLE IF NOT EXISTS events (
                id SERIAL PRIMARY KEY,
                photographer_uuid VARCHAR(36),
                photographer_name VARCHAR(150) NOT NULL,
                event_name VARCHAR(150) NOT NULL,
                event_location VARCHAR(255) NOT NULL,
                event_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_deleted BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE,
                uuid VARCHAR(36) DEFAULT gen_random_uuid()
            )
        ''')

 
 
        # Event Photo Count Table
            cur.execute('''
                CREATE TABLE IF NOT EXISTS event_photo_count (
                    id SERIAL PRIMARY KEY,
                    event_uuid UUID UNIQUE NOT NULL,
                    total_photos INT DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
 
        conn.commit()
 
 