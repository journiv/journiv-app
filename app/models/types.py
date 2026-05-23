"""
Shared SQLAlchemy column types for models.
TODO: App already has other local JSONType helpers in older models like entry.py and moment.py that should be refactored to use this one.
"""

from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import JSON


def JSONType():
    return JSONB().with_variant(JSON, "sqlite")
