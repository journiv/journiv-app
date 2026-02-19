"""Add structured location/weather fields and remove legacy fields

Revision ID: d8f3a9e2b1c4
Revises: f0cf0baa6c0d
Create Date: 2026-01-07 00:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "d8f3a9e2b1c4"
down_revision = "f0cf0baa6c0d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Replace legacy location/weather fields with structured JSON fields.

    Removed fields:
    - location: Legacy location string (unused, no production data)
    - weather: Legacy weather string (unused, no production data)

    New fields:
    - location_json: Structured location data (name, coordinates, timezone)
    - latitude: GPS latitude
    - longitude: GPS longitude
    - weather_json: Structured weather data (temp, condition, code)
    - weather_summary: Human-readable weather summary
    """
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    is_postgres = connection.dialect.name == "postgresql"

    entry_columns = {col["name"] for col in inspector.get_columns("entry")}

    # Drop legacy fields (no production data, safe to remove)
    if "location" in entry_columns:
        op.drop_column("entry", "location")
    if "weather" in entry_columns:
        op.drop_column("entry", "weather")

    # Add location_json (use JSONB for PostgreSQL, JSON for others)
    if "location_json" not in entry_columns:
        if is_postgres:
            op.add_column(
                "entry",
                sa.Column("location_json", postgresql.JSONB, nullable=True),
            )
        else:
            op.add_column(
                "entry",
                sa.Column("location_json", sa.JSON, nullable=True),
            )

    # Add latitude
    if "latitude" not in entry_columns:
        op.add_column(
            "entry",
            sa.Column("latitude", sa.Float, nullable=True),
        )

    # Add longitude
    if "longitude" not in entry_columns:
        op.add_column(
            "entry",
            sa.Column("longitude", sa.Float, nullable=True),
        )

    # Add weather_json (use JSONB for PostgreSQL, JSON for others)
    if "weather_json" not in entry_columns:
        if is_postgres:
            op.add_column(
                "entry",
                sa.Column("weather_json", postgresql.JSONB, nullable=True),
            )
        else:
            op.add_column(
                "entry",
                sa.Column("weather_json", sa.JSON, nullable=True),
            )

    # Add weather_summary
    if "weather_summary" not in entry_columns:
        op.add_column(
            "entry",
            sa.Column("weather_summary", sa.Text, nullable=True),
        )

    # Create indexes for geospatial queries
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("entry")}

    if "idx_entry_latitude_longitude" not in existing_indexes:
        op.create_index(
            "idx_entry_latitude_longitude",
            "entry",
            ["latitude", "longitude"],
            unique=False,
        )


def downgrade() -> None:
    """Restore legacy location/weather fields and remove new structured fields."""
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    # Drop index
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("entry")}
    if "idx_entry_latitude_longitude" in existing_indexes:
        op.drop_index("idx_entry_latitude_longitude", table_name="entry")

    # Drop new structured columns
    entry_columns = {col["name"] for col in inspector.get_columns("entry")}

    if "weather_summary" in entry_columns:
        op.drop_column("entry", "weather_summary")
    if "weather_json" in entry_columns:
        op.drop_column("entry", "weather_json")
    if "longitude" in entry_columns:
        op.drop_column("entry", "longitude")
    if "latitude" in entry_columns:
        op.drop_column("entry", "latitude")
    if "location_json" in entry_columns:
        op.drop_column("entry", "location_json")

    # Restore legacy fields (for migration reversibility)
    if "location" not in entry_columns:
        op.add_column(
            "entry",
            sa.Column("location", sa.String(200), nullable=True),
        )
    if "weather" not in entry_columns:
        op.add_column(
            "entry",
            sa.Column("weather", sa.String(100), nullable=True),
        )
