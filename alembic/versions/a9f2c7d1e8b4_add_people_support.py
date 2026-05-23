"""add people support

Revision ID: a9f2c7d1e8b4
Revises: 5b6c7d8e9f0a
Create Date: 2026-03-02 10:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9f2c7d1e8b4"
down_revision: Union[str, Sequence[str], None] = "5b6c7d8e9f0a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "person",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("normalized_name", sa.String(length=120), nullable=False),
        sa.Column("nickname", sa.String(length=120), nullable=True),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column("profile_image_path", sa.String(length=512), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "normalized_name", name="uq_person_user_normalized_name"
        ),
        sa.CheckConstraint("length(name) > 0", name="check_person_name_not_empty"),
        sa.CheckConstraint(
            "length(normalized_name) > 0", name="check_person_normalized_name_not_empty"
        ),
        sa.CheckConstraint(
            "normalized_name = lower(normalized_name)",
            name="check_person_normalized_name_lowercase",
        ),
    )
    op.create_index(op.f("ix_person_user_id"), "person", ["user_id"], unique=False)
    op.create_index(op.f("ix_person_name"), "person", ["name"], unique=False)
    op.create_index(
        op.f("ix_person_normalized_name"), "person", ["normalized_name"], unique=False
    )
    op.create_index(
        op.f("ix_person_archived_at"), "person", ["archived_at"], unique=False
    )
    op.create_index(
        "idx_person_user_archived_name",
        "person",
        ["user_id", "archived_at", "name"],
        unique=False,
    )

    op.create_table(
        "person_group",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("color_value", sa.BigInteger(), nullable=True),
        sa.Column("icon", sa.String(length=50), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("stable_key", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "stable_key", name="uq_person_group_user_stable_key"
        ),
        sa.CheckConstraint("length(name) > 0", name="ck_person_group_name_non_empty"),
    )
    op.create_index(
        op.f("ix_person_group_stable_key"), "person_group", ["stable_key"], unique=False
    )
    op.create_index(
        op.f("ix_person_group_user_id"), "person_group", ["user_id"], unique=False
    )
    op.create_index(
        "idx_person_group_user_name", "person_group", ["user_id", "name"], unique=True
    )

    op.create_table(
        "person_group_link",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("person_group_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["person_group_id"], ["person_group.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("person_group_id", "person_id"),
    )
    op.create_index(
        "idx_person_group_link_person_id",
        "person_group_link",
        ["person_id"],
        unique=False,
    )

    op.create_table(
        "moment_person_link",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("moment_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["moment_id"], ["moment.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("moment_id", "person_id"),
    )
    op.create_index(
        "idx_moment_person_link_person_moment",
        "moment_person_link",
        ["person_id", "moment_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_person_group_link_person_id", table_name="person_group_link")
    op.drop_table("person_group_link")

    op.drop_index("idx_person_group_user_name", table_name="person_group")
    op.drop_index(op.f("ix_person_group_user_id"), table_name="person_group")
    op.drop_index(op.f("ix_person_group_stable_key"), table_name="person_group")
    op.drop_table("person_group")

    op.drop_index(
        "idx_moment_person_link_person_moment", table_name="moment_person_link"
    )
    op.drop_table("moment_person_link")

    op.drop_index("idx_person_user_archived_name", table_name="person")
    op.drop_index(op.f("ix_person_archived_at"), table_name="person")
    op.drop_index(op.f("ix_person_normalized_name"), table_name="person")
    op.drop_index(op.f("ix_person_name"), table_name="person")
    op.drop_index(op.f("ix_person_user_id"), table_name="person")
    op.drop_table("person")
