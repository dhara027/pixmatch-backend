"""
Gunicorn configuration for production.
Uses sync workers — reliable on Render free tier (512 MB).
preload_app is disabled — psycopg2 connection pools are NOT fork-safe.
"""
import os as _os

# Bind address — Render injects $PORT; fallback to 5000 for local dev
bind = f"0.0.0.0:{_os.environ.get('PORT', '5000')}"

# sync workers: one request per worker, no threading complexity.
# Render free tier has 512 MB RAM and large ML deps (insightface/onnxruntime),
# so gthread's extra thread overhead can cause OOM or stall port binding.
# WEB_CONCURRENCY=1 is set explicitly on Render to ensure exactly 1 worker.
worker_class = "sync"
workers = int(_os.environ.get("WEB_CONCURRENCY", "1"))

# Timeouts — generous for face match downloads, but gunicorn will kill workers
# that exceed this limit.
timeout = 120
keepalive = 5
graceful_timeout = 30

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(D)sµs'

# Process naming
proc_name = "pixmatch-api"

# Security
limit_request_line = 8190
limit_request_fields = 100

# Only trust X-Forwarded-For from the nginx container (127.0.0.1 for localhost,
# or the Docker bridge network IP). Using "*" trusts ALL clients which allows
# IP spoofing to bypass rate limiting.
# On managed platforms (Render, Railway, Heroku) all traffic comes through the
# platform's load balancer at dynamic IPs — trust forwarded headers from all upstream.
forwarded_allow_ips = "*"

# IMPORTANT: preload_app MUST be False.
# psycopg2 ThreadedConnectionPool is not fork-safe — connections created in the
# parent process get corrupted in forked workers, causing silent query failures.
# Each worker initialises its own pool via create_app() after fork.
preload_app = False


def on_starting(server):
    server.log.info("Starting PixMatch API server (sync, workers=%d)", workers)


def worker_exit(server, worker):
    from app.extensions.database import close_pool
    close_pool()
