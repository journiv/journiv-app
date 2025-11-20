"""Make user name field required

Revision ID: 7c52fcc89c83
Revises: 6b2d62d09dd8
Create Date: 2025-01-27 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7c52fcc89c83'
down_revision = '6b2d62d09dd8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    is_sqlite = connection.dialect.name == "sqlite"

    if is_sqlite:
        op.execute(sa.text("UPDATE user SET name = 'No Name' WHERE name IS NULL OR name = ''"))
    else:
        op.execute(sa.text('UPDATE "user" SET name = \'No Name\' WHERE name IS NULL OR name = \'\''))

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
            SELECT id, created_at, updated_at, email, password,
                   COALESCE(NULLIF(name, ''), 'No Name'), is_active, profile_picture_url, last_login_at
            FROM user
        ''')

        op.execute('DROP TABLE user')
        op.execute('ALTER TABLE user_new RENAME TO user')

        op.execute('CREATE INDEX idx_user_active ON user (is_active)')
        op.execute('CREATE UNIQUE INDEX ix_user_email ON user (email)')
        op.execute('CREATE INDEX ix_user_id ON user (id)')
    else:
        op.drop_constraint('check_name_not_empty', 'user', type_='check')

        op.alter_column('user', 'name',
                       existing_type=sa.String(length=100),
                       nullable=False,
                       existing_nullable=True)

        op.create_check_constraint(
            'check_name_not_empty',
            'user',
            'length(name) > 0',
        )


def downgrade() -> None:
    connection = op.get_bind()
    is_sqlite = connection.dialect.name == "sqlite"

    if not is_sqlite:
        op.drop_constraint('check_name_not_empty', 'user', type_='check')

    if is_sqlite:
        op.execute('''
            CREATE TABLE user_new (
                id TEXT NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                email TEXT NOT NULL,
                password TEXT NOT NULL,
                name TEXT,
                is_active BOOLEAN NOT NULL,
                profile_picture_url TEXT,
                last_login_at DATETIME,
                PRIMARY KEY (id),
                UNIQUE (email),
                CHECK(name IS NULL OR length(name) > 0)
            )
        ''')

        op.execute('''
            INSERT INTO user_new
            SELECT id, created_at, updated_at, email, password,
                   CASE WHEN name = 'No Name' THEN NULL ELSE name END,
                   is_active, profile_picture_url, last_login_at
            FROM user
        ''')

        op.execute('DROP TABLE user')
        op.execute('ALTER TABLE user_new RENAME TO user')

        op.execute('CREATE INDEX idx_user_active ON user (is_active)')
        op.execute('CREATE UNIQUE INDEX ix_user_email ON user (email)')
        op.execute('CREATE INDEX ix_user_id ON user (id)')
    else:
        op.alter_column('user', 'name',
                       existing_type=sa.String(length=100),
                       nullable=True,
                       existing_nullable=False)

        op.create_check_constraint(
            'check_name_not_empty',
            'user',
            'name IS NULL OR length(name) > 0',
        )

