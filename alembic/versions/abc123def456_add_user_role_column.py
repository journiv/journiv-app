"""Add user role column for admin/user management

Revision ID: abc123def456
Revises: 7c52fcc89c83
Create Date: 2025-01-28 00:00:00.000000

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'abc123def456'
down_revision = '7c52fcc89c83'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add role column to user table and promote first user to admin."""
    connection = op.get_bind()
    is_sqlite = connection.dialect.name == "sqlite"

    if is_sqlite:
        op.execute('''
            CREATE TABLE user_new (
                id TEXT NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                email TEXT NOT NULL,
                password TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                is_active BOOLEAN NOT NULL,
                profile_picture_url TEXT,
                last_login_at DATETIME,
                PRIMARY KEY (id),
                UNIQUE (email),
                CHECK(length(name) > 0)
            )
        ''')

        op.execute('''
            INSERT INTO user_new
            SELECT id, created_at, updated_at, email, password, name,
                   'user', is_active, profile_picture_url, last_login_at
            FROM user
        ''')

        op.execute('''
            UPDATE user_new
            SET role = 'admin'
            WHERE id = (
                SELECT id FROM user_new
                ORDER BY created_at ASC
                LIMIT 1
            )
        ''')

        op.execute('DROP TABLE user')
        op.execute('ALTER TABLE user_new RENAME TO user')

        op.execute('CREATE INDEX idx_user_active ON user (is_active)')
        op.execute('CREATE UNIQUE INDEX ix_user_email ON user (email)')
        op.execute('CREATE INDEX ix_user_id ON user (id)')
    else:
        op.add_column('user', sa.Column('role', sa.String(length=20), nullable=False, server_default='user'))

        op.execute(sa.text('''
            UPDATE "user"
            SET role = 'admin'
            WHERE id = (
                SELECT id FROM "user"
                ORDER BY created_at ASC
                LIMIT 1
            )
        '''))


def downgrade() -> None:
    """Remove role column from user table."""
    connection = op.get_bind()
    is_sqlite = connection.dialect.name == "sqlite"

    if is_sqlite:
        op.execute('''
            CREATE TABLE user_new (
                id TEXT NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                email TEXT NOT NULL,
                password TEXT NOT NULL,
                name TEXT NOT NULL,
                is_active BOOLEAN NOT NULL,
                profile_picture_url TEXT,
                last_login_at DATETIME,
                PRIMARY KEY (id),
                UNIQUE (email),
                CHECK(length(name) > 0)
            )
        ''')

        op.execute('''
            INSERT INTO user_new
            SELECT id, created_at, updated_at, email, password, name,
                   is_active, profile_picture_url, last_login_at
            FROM user
        ''')

        op.execute('DROP TABLE user')
        op.execute('ALTER TABLE user_new RENAME TO user')

        op.execute('CREATE INDEX idx_user_active ON user (is_active)')
        op.execute('CREATE UNIQUE INDEX ix_user_email ON user (email)')
        op.execute('CREATE INDEX ix_user_id ON user (id)')
    else:
        op.drop_column('user', 'role')
