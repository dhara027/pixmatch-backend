"""
WSGI entry point. Use with gunicorn:
  gunicorn -c gunicorn.conf.py "main:create_app()"
"""
from dotenv import load_dotenv
load_dotenv()

from app import create_app

application = create_app()

if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 5000))
    # NOTE: Only for local dev. Never use Flask dev server in production.
    application.run(host="0.0.0.0", port=port, debug=False)
