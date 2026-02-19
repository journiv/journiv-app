"""add_media_count

Revision ID: b4f45de4db7f
Revises: 0ad99dfbe7ec
Create Date: 2026-01-20 01:13:24.877927

This migration adds media_count and removes has_media (if present).
"""
import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision = 'b4f45de4db7f'
down_revision = '0ad99dfbe7ec'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add media_count and cleanup has_media."""

    # Detect database dialect
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    inspector = sa.inspect(bind)
    columns = [x['name'] for x in inspector.get_columns('entry')]
    indexes = [x['name'] for x in inspector.get_indexes('entry')]

    # Step 1: Cleanup old has_media artifacts IF they exist
    if dialect_name == 'postgresql':
        op.execute(text("DROP TRIGGER IF EXISTS entry_media_has_media_trigger ON entry_media"))
        op.execute(text("DROP FUNCTION IF EXISTS update_entry_has_media_flag()"))
    elif dialect_name == 'sqlite':
        op.execute(text("DROP TRIGGER IF EXISTS entry_media_insert_trigger"))
        op.execute(text("DROP TRIGGER IF EXISTS entry_media_delete_trigger"))

    if 'has_media' in columns:
        with op.batch_alter_table('entry', schema=None) as batch_op:
            if 'ix_entry_has_media' in indexes:
                batch_op.drop_index('ix_entry_has_media')
            batch_op.drop_column('has_media')

    # Step 2: Add media_count column
    if 'media_count' not in columns:
        with op.batch_alter_table('entry', schema=None) as batch_op:
            batch_op.add_column(
                sa.Column('media_count', sa.Integer(), server_default='0', nullable=False)
            )
            batch_op.create_index('ix_entry_media_count', ['media_count'], unique=False)

    # Step 3: Backfill media_count from existing data
    op.execute(text("""
        UPDATE entry
        SET media_count = (
            SELECT COUNT(*)
            FROM entry_media
            WHERE entry_media.entry_id = entry.id
        )
    """))

    # Step 4: Create triggers
    if dialect_name == 'postgresql':
        # PostgreSQL: Create function and trigger with increment/decrement logic
        op.execute(text("""
            CREATE OR REPLACE FUNCTION update_entry_media_count()
            RETURNS TRIGGER AS $$
            BEGIN
                IF (TG_OP = 'INSERT') THEN
                    UPDATE entry
                    SET media_count = media_count + 1
                    WHERE id = NEW.entry_id;
                    RETURN NEW;
                ELSIF (TG_OP = 'DELETE') THEN
                    UPDATE entry
                    SET media_count = GREATEST(media_count - 1, 0)
                    WHERE id = OLD.entry_id;
                    RETURN OLD;
                END IF;
            END;
            $$ LANGUAGE plpgsql;
        """))

        op.execute(text("""
            CREATE TRIGGER entry_media_count_trigger
            AFTER INSERT OR DELETE ON entry_media
            FOR EACH ROW
            EXECUTE FUNCTION update_entry_media_count();
        """))

    elif dialect_name == 'sqlite':
        # SQLite: Create separate triggers for INSERT and DELETE
        op.execute(text("""
            CREATE TRIGGER entry_media_count_insert_trigger
            AFTER INSERT ON entry_media
            FOR EACH ROW
            BEGIN
                UPDATE entry
                SET media_count = media_count + 1
                WHERE id = NEW.entry_id;
            END;
        """))

        op.execute(text("""
            CREATE TRIGGER entry_media_count_delete_trigger
            AFTER DELETE ON entry_media
            FOR EACH ROW
            BEGIN
                UPDATE entry
                SET media_count = MAX(media_count - 1, 0)
                WHERE id = OLD.entry_id;
            END;
        """))


def downgrade() -> None:
    """Remove media_count."""

    bind = op.get_bind()
    dialect_name = bind.dialect.name
    inspector = sa.inspect(bind)
    columns = [x['name'] for x in inspector.get_columns('entry')]

    # Step 1: Drop triggers
    if dialect_name == 'postgresql':
        op.execute(text("DROP TRIGGER IF EXISTS entry_media_count_trigger ON entry_media"))
        op.execute(text("DROP FUNCTION IF EXISTS update_entry_media_count()"))
    elif dialect_name == 'sqlite':
        op.execute(text("DROP TRIGGER IF EXISTS entry_media_count_insert_trigger"))
        op.execute(text("DROP TRIGGER IF EXISTS entry_media_count_delete_trigger"))

    # Step 2: Remove media_count column
    if 'media_count' in columns:
        with op.batch_alter_table('entry', schema=None) as batch_op:
            batch_op.drop_index('ix_entry_media_count')
            batch_op.drop_column('media_count')
