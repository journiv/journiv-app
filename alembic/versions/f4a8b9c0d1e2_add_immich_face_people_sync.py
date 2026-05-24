"""add immich face people sync

Revision ID: f4a8b9c0d1e2
Revises: a9f2c7d1e8b4
Create Date: 2026-05-11 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4a8b9c0d1e2"
down_revision: Union[str, Sequence[str], None] = "a9f2c7d1e8b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_type():
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "person_external_identity",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("integration_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("external_person_id", sa.String(length=255), nullable=False),
        sa.Column("external_name", sa.String(length=255), nullable=True),
        sa.Column("external_thumbnail_asset_id", sa.String(length=255), nullable=True),
        sa.Column("external_face_id", sa.String(length=255), nullable=True),
        sa.Column("feature_face_asset_id", sa.String(length=255), nullable=True),
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sync_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_metadata", _json_type(), nullable=True),
        sa.ForeignKeyConstraint(["integration_id"], ["integration.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "integration_id",
            "external_person_id",
            name="uq_person_external_identity_provider_person",
        ),
        sa.UniqueConstraint(
            "person_id",
            "integration_id",
            "provider",
            name="uq_person_external_identity_person_provider",
        ),
    )
    op.create_index(op.f("ix_person_external_identity_user_id"), "person_external_identity", ["user_id"], unique=False)
    op.create_index(op.f("ix_person_external_identity_person_id"), "person_external_identity", ["person_id"], unique=False)
    op.create_index(op.f("ix_person_external_identity_integration_id"), "person_external_identity", ["integration_id"], unique=False)
    op.create_index(op.f("ix_person_external_identity_provider"), "person_external_identity", ["provider"], unique=False)
    op.create_index(op.f("ix_person_external_identity_external_person_id"), "person_external_identity", ["external_person_id"], unique=False)
    op.create_index(
        "idx_person_external_identity_user_provider_sync",
        "person_external_identity",
        ["user_id", "provider", "sync_enabled"],
        unique=False,
    )
    op.create_table(
        "immich_asset_face",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("integration_id", sa.Uuid(), nullable=False),
        sa.Column("external_asset_id", sa.String(length=255), nullable=False),
        sa.Column("external_face_id", sa.String(length=255), nullable=False),
        sa.Column("external_person_id", sa.String(length=255), nullable=True),
        sa.Column("person_id", sa.Uuid(), nullable=True),
        sa.Column("bounding_box_x1", sa.Integer(), nullable=True),
        sa.Column("bounding_box_y1", sa.Integer(), nullable=True),
        sa.Column("bounding_box_x2", sa.Integer(), nullable=True),
        sa.Column("bounding_box_y2", sa.Integer(), nullable=True),
        sa.Column("image_width", sa.Integer(), nullable=True),
        sa.Column("image_height", sa.Integer(), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=True),
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("raw_metadata", _json_type(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["integration_id"], ["integration.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("integration_id", "external_face_id", name="uq_immich_asset_face_integration_face"),
    )
    op.create_index(op.f("ix_immich_asset_face_user_id"), "immich_asset_face", ["user_id"], unique=False)
    op.create_index(op.f("ix_immich_asset_face_integration_id"), "immich_asset_face", ["integration_id"], unique=False)
    op.create_index(op.f("ix_immich_asset_face_external_asset_id"), "immich_asset_face", ["external_asset_id"], unique=False)
    op.create_index(op.f("ix_immich_asset_face_external_face_id"), "immich_asset_face", ["external_face_id"], unique=False)
    op.create_index(op.f("ix_immich_asset_face_external_person_id"), "immich_asset_face", ["external_person_id"], unique=False)
    op.create_index(op.f("ix_immich_asset_face_person_id"), "immich_asset_face", ["person_id"], unique=False)
    op.create_index(
        "idx_immich_asset_face_integration_asset",
        "immich_asset_face",
        ["integration_id", "external_asset_id"],
        unique=False,
    )
    op.create_index(
        "idx_immich_asset_face_integration_person",
        "immich_asset_face",
        ["integration_id", "external_person_id"],
        unique=False,
    )
    op.create_index(
        "idx_immich_asset_face_user_person",
        "immich_asset_face",
        ["user_id", "person_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_immich_asset_face_user_person", table_name="immich_asset_face")
    op.drop_index("idx_immich_asset_face_integration_person", table_name="immich_asset_face")
    op.drop_index("idx_immich_asset_face_integration_asset", table_name="immich_asset_face")
    op.drop_index(op.f("ix_immich_asset_face_person_id"), table_name="immich_asset_face")
    op.drop_index(op.f("ix_immich_asset_face_external_person_id"), table_name="immich_asset_face")
    op.drop_index(op.f("ix_immich_asset_face_external_face_id"), table_name="immich_asset_face")
    op.drop_index(op.f("ix_immich_asset_face_external_asset_id"), table_name="immich_asset_face")
    op.drop_index(op.f("ix_immich_asset_face_integration_id"), table_name="immich_asset_face")
    op.drop_index(op.f("ix_immich_asset_face_user_id"), table_name="immich_asset_face")
    op.drop_table("immich_asset_face")

    op.drop_index("idx_person_external_identity_user_provider_sync", table_name="person_external_identity")
    op.drop_index(op.f("ix_person_external_identity_external_person_id"), table_name="person_external_identity")
    op.drop_index(op.f("ix_person_external_identity_provider"), table_name="person_external_identity")
    op.drop_index(op.f("ix_person_external_identity_integration_id"), table_name="person_external_identity")
    op.drop_index(op.f("ix_person_external_identity_person_id"), table_name="person_external_identity")
    op.drop_index(op.f("ix_person_external_identity_user_id"), table_name="person_external_identity")
    op.drop_table("person_external_identity")
