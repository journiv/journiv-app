"""add publishing fields

Revision ID: a1a2b3c4d5e6
Revises: f3b4c5d6e7f8
Create Date: 2026-02-12 10:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "a1a2b3c4d5e6"
down_revision = "f3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add publishing fields to entry table
    # All fields are nullable or have server defaults to avoid affecting existing entries

    # public_id: nullable unique string (generated on first publish)
    op.add_column("entry", sa.Column("public_id", sa.String(length=12), nullable=True))
    op.create_index(op.f("ix_entry_public_id"), "entry", ["public_id"], unique=True)

    # slug: nullable unique string (generated from title on first publish)
    op.add_column("entry", sa.Column("slug", sa.String(length=255), nullable=True))
    op.create_index(op.f("ix_entry_slug"), "entry", ["slug"], unique=True)

    # is_published: boolean with server default false
    op.add_column(
        "entry",
        sa.Column("is_published", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_index(
        op.f("ix_entry_is_published"), "entry", ["is_published"], unique=False
    )

    # is_indexed: boolean with server default false (search engine visibility)
    op.add_column(
        "entry",
        sa.Column("is_indexed", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    # Remove publishing fields in reverse order
    op.drop_column("entry", "is_indexed")
    op.drop_index(op.f("ix_entry_is_published"), table_name="entry")
    op.drop_column("entry", "is_published")
    op.drop_index(op.f("ix_entry_slug"), table_name="entry")
    op.drop_column("entry", "slug")
    op.drop_index(op.f("ix_entry_public_id"), table_name="entry")
    op.drop_column("entry", "public_id")
