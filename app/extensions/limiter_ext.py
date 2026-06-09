"""
Rate-limiter extension.

Import `limiter` from here in blueprints/routes — never from `app`,
which would create a circular import since app/__init__.py imports blueprints.
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# RATELIMIT_SWALLOW_ERRORS=True is set in app/__init__.py Flask config so that
# Redis unavailability (cold start) never blocks requests or the health probe.
limiter: Limiter = Limiter(get_remote_address)
