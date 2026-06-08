"""
Events module — schemas, repository, service, routes.
"""

# ─── schemas.py ───────────────────────────────────────────────────────────────
from marshmallow import Schema, fields, validate


class CreateEventSchema(Schema):
    event_name = fields.Str(required=True, validate=validate.Length(min=2, max=200))
    event_location = fields.Str(required=True, validate=validate.Length(min=2, max=500))
    event_date = fields.Date(required=True)
    photographer_name = fields.Str(required=True, validate=validate.Length(min=2, max=150))


class EventListQuerySchema(Schema):
    page = fields.Int(load_default=1, validate=validate.Range(min=1))
    page_size = fields.Int(load_default=10, validate=validate.Range(min=1, max=100))
