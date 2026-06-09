"""
Rate-limiter extension.

Import `limiter` from here in blueprints/routes — never from `app`,
which would create a circular import since app/__init__.py imports blueprints.
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# fail_on_storage_error=False: if Redis is unavailable (cold start, transient
# network issue), requests are allowed through rather than returning 500.
# This prevents Render's health probe from failing due to a Redis blip.
limiter: Limiter = Limiter(get_remote_address, fail_on_storage_error=False)
