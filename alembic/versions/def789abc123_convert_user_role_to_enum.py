"""Convert user role column from VARCHAR to enum type

Revision ID: def789abc123
Revises: abc123def456
Create Date: 2025-01-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'def789abc123'
down_revision = 'abc123def456'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Convert user.role from VARCHAR to enum type.

    For PostgreSQL:
    - Create enum type 'user_role_enum' with values ('admin', 'user')
    - Drop existing server default temporarily
    - Convert role column from VARCHAR to enum using USING clause
    - Re-add server default as enum value

    For SQLite:
    - No changes needed (SQLite doesn't support native enums)
    - SQLAlchemy will use CHECK constraint instead
    """
    connection = op.get_bind()
    is_sqlite = connection.dialect.name == "sqlite"

    if not is_sqlite:
        # PostgreSQL: Create enum type and convert column

        # Check if the enum type already exists
        result = connection.execute(sa.text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'user_role_enum'
            )
        """))
        enum_exists = result.scalar()

        # Create the enum type if it doesn't exist
        # Using native PostgreSQL ENUM for better type safety
        if not enum_exists:
            op.execute("CREATE TYPE user_role_enum AS ENUM ('admin', 'user')")

        # Drop the server default temporarily (it's a string, incompatible with enum)
        op.execute('ALTER TABLE "user" ALTER COLUMN role DROP DEFAULT')

        # Validate that all role values are valid before conversion
        result = connection.execute(sa.text("""
            SELECT COUNT(*) FROM "user"
            WHERE role NOT IN ('admin', 'user')
        """))
        invalid_count = result.scalar()
        if invalid_count > 0:
            raise ValueError(
                f"Found {invalid_count} users with invalid role values. "
                "Please fix the data before running this migration."
            )

        # Convert the column type using USING clause to cast existing values
        op.execute("""
            ALTER TABLE "user"
            ALTER COLUMN role TYPE user_role_enum
            USING role::user_role_enum
        """)

        # Re-add the server default as an enum value
        op.execute("ALTER TABLE \"user\" ALTER COLUMN role SET DEFAULT 'user'::user_role_enum")

    # SQLite: No migration needed
    # SQLAlchemy will handle enum validation at the application level
    # The column remains VARCHAR with server_default='user'


def downgrade() -> None:
    """
    Revert user.role from enum back to VARCHAR.

    For PostgreSQL:
    - Drop enum server default
    - Convert role column from enum back to VARCHAR(20)
    - Re-add string server default
    - Drop the user_role_enum type

    For SQLite:
    - No changes needed
    """
    connection = op.get_bind()
    is_sqlite = connection.dialect.name == "sqlite"

    if not is_sqlite:
        # PostgreSQL: Convert back to VARCHAR and drop enum type

        # Drop the enum default
        op.execute('ALTER TABLE "user" ALTER COLUMN role DROP DEFAULT')

        # Convert column back to VARCHAR(20), casting enum values to text
        op.execute("""
            ALTER TABLE "user"
            ALTER COLUMN role TYPE VARCHAR(20)
            USING role::text
        """)

        # Re-add the string server default
        op.execute("ALTER TABLE \"user\" ALTER COLUMN role SET DEFAULT 'user'")

        # Drop the enum type
        op.execute("DROP TYPE user_role_enum")

    # SQLite: No downgrade needed
