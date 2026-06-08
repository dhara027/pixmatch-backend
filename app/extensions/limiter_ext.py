"""
Rate-limiter extension.

Import `limiter` from here in blueprints/routes — never from `app`,
which would create a circular import since app/__init__.py imports blueprints.
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter: Limiter = Limiter(get_remote_address)
