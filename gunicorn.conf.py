"""
Gunicorn configuration for production.
Uses gthread workers for better concurrency on I/O-bound workloads.
preload_app is disabled — psycopg2 connection pools are NOT fork-safe.
"""
import multiprocessing

# Bind address — Render assigns a dynamic $PORT; fallback to 5000 for local dev
import os as _os
bind = f"0.0.0.0:{_os.environ.get('PORT', '5000')}"

# gthread workers: each worker handles requests concurrently via threads.
# For I/O-bound Flask (Cloudinary uploads, Redis, DB calls), this is far more
# efficient than sync workers which block the entire process on every I/O wait.
worker_class = "gthread"
threads = 4
workers = max(2, multiprocessing.cpu_count())  # fewer workers, more threads each

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
    server.log.info("Starting PixMatch API server (gthread, workers=%d, threads=%d)", workers, threads)


def worker_exit(server, worker):
    from app.extensions.database import close_pool
    close_pool()
