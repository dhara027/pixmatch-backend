from flask import Flask
from flask_cors import CORS
from models import init_db
from auth_routes import auth_bp
from photo_routes import photo_bp
from face_match_routes import face_match_bp
import os
from dotenv import load_dotenv
from event_routes import event_bp
 
load_dotenv()
 
def create_app():
    app = Flask(__name__)
 
    # CORS configuration
    CORS(app,
         resources={r"/*": {"origins": os.getenv("FRONTEND_URL")}},
         supports_credentials=True)
 
    # Initialize database
    init_db()
 
    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(event_bp, url_prefix='/api/event')
    app.register_blueprint(photo_bp, url_prefix='/api/photo')
    app.register_blueprint(face_match_bp, url_prefix='/api/face')
 
 
    return app
 
if __name__ == '__main__':
    app = create_app()
    app.run(
        debug=os.getenv('FLASK_ENV') == 'development',
        port=int(os.getenv('PORT', 5000))
    )
 
 