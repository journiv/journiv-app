"""add shared journals

Revision ID: 76d57ea56eb6
Revises: a3c5e7f9b1d2
Create Date: 2026-10-15 20:38:50.286621
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "76d57ea56eb6"
down_revision = "a3c5e7f9b1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add journal memberships and entry author tracking."""
    connection = op.get_bind()
    is_sqlite = connection.dialect.name == "sqlite"
    # SQLite has no reusable named enum type, so its constraint below carries validation.
    if not is_sqlite:
        permission = sa.Enum("readonly", "edit", name="journal_permission_enum")
    else:
        permission = sa.String(length=16)

    op.create_table(
        "journal_member",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("journal_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("permission", permission, nullable=False),
        sa.CheckConstraint("permission IN ('readonly', 'edit')", name="ck_journal_member_permission"),
        sa.ForeignKeyConstraint(["journal_id"], ["journal.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("journal_id", "user_id", name="uq_journal_member_journal_user"),
    )
    op.create_index("ix_journal_member_user_id", "journal_member", ["user_id"])

    op.add_column("entry", sa.Column("created_by_user_id", sa.Uuid(), nullable=True))
    op.create_index("ix_entry_created_by_user_id", "entry", ["created_by_user_id"])
    with op.batch_alter_table("entry") as batch_op:
        batch_op.create_foreign_key(
            "fk_entry_created_by_user_id_user",
            "user",
            ["created_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.execute(
        """
        UPDATE entry
        SET created_by_user_id = entry.user_id
        """
        if not is_sqlite
        else """
        UPDATE entry
        SET created_by_user_id = user_id
        """
    )


def downgrade() -> None:
    """Remove journal memberships and entry author tracking."""
    # Restore journal ownership before discarding collaborator attribution.
    op.execute(
        """
        UPDATE entry
        SET user_id = (
            SELECT user_id
            FROM journal
            WHERE journal.id = entry.journal_id
        )
        """
    )
    op.drop_index("ix_entry_created_by_user_id", table_name="entry")
    with op.batch_alter_table("entry") as batch_op:
        batch_op.drop_constraint("fk_entry_created_by_user_id_user", type_="foreignkey")
        batch_op.drop_column("created_by_user_id")
    op.drop_index("ix_journal_member_user_id", table_name="journal_member")
    op.drop_table("journal_member")
    if op.get_bind().dialect.name != "sqlite":
        op.execute("DROP TYPE journal_permission_enum")
