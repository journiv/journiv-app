"""Allow entry content to be nullable.

Revision ID: 9b1c2d3e4f5g
Revises: e7c4a1b2c3d4
Create Date: 2026-01-07 00:00:00.000000
"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "9b1c2d3e4f5g"
down_revision = "e7c4a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "entry" not in inspector.get_table_names():
        return

    entry_columns = {col["name"] for col in inspector.get_columns("entry")}
    if "content" not in entry_columns:
        return

    check_constraints = {c["name"] for c in inspector.get_check_constraints("entry")}

    with op.batch_alter_table("entry") as batch_op:
        if "check_content_not_empty" in check_constraints:
            batch_op.drop_constraint("check_content_not_empty", type_="check")
        batch_op.alter_column(
            "content",
            existing_type=sa.String(length=100000),
            nullable=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "entry" not in inspector.get_table_names():
        return

    entry_columns = {col["name"] for col in inspector.get_columns("entry")}
    if "content" not in entry_columns:
        return

    op.execute(
        sa.text("UPDATE entry SET content = '' WHERE content IS NULL")
    )

    with op.batch_alter_table("entry") as batch_op:
        batch_op.alter_column(
            "content",
            existing_type=sa.String(length=100000),
            nullable=False,
        )
        batch_op.create_check_constraint(
            "check_content_not_empty",
            "length(content) > 0",
        )
