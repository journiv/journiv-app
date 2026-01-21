"""change media duration to float

Revision ID: 885e3d7a9b2c
Revises: b4f45de4db7f
Create Date: 2026-01-21 08:12:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '885e3d7a9b2c'
down_revision = 'b4f45de4db7f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Change duration column from Integer to Float in entry_media table
    # Using type_ to handle the cast if necessary, though Float is generally compatible
    with op.batch_alter_table('entry_media', schema=None) as batch_op:
        batch_op.alter_column('duration',
               existing_type=sa.INTEGER(),
               type_=sa.Float(),
               existing_nullable=True)


def downgrade() -> None:
    # Change duration column back from Float to Integer
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        # PostgreSQL requires explicit USING clause for type conversion
        op.execute("""
            ALTER TABLE entry_media
            ALTER COLUMN duration TYPE INTEGER
            USING round(duration)::integer
        """)
    else:
        # SQLite handles the conversion automatically
        with op.batch_alter_table('entry_media', schema=None) as batch_op:
            batch_op.alter_column('duration',
                   existing_type=sa.Float(),
                   type_=sa.Integer(),
                   existing_nullable=True)
