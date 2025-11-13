"""
Alembic environment configuration tailored for SQLModel models.

The key customization is a renderer that converts SQLModel-specific column
types (e.g., AutoString) into portable SQLAlchemy primitives so generated
migrations run cleanly on both SQLite and PostgreSQL.
Currently this does not work as expected so the migration has been patched to use the correct types. See scripts/fix_migration_imports.py for the patch.
"""
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.sql.sqltypes import Uuid

try:  # Alembic ≥1.10
    from alembic.autogenerate.api import AutogenContext
except ImportError:  # pragma: no cover - fallback for older Alembic
    AutogenContext = Any  # type: ignore[assignment]

from alembic.autogenerate import renderers
from app.core.config import settings
from app.models import *  # noqa: F401,F403  (needed for metadata discovery)
from sqlmodel import SQLModel
from sqlmodel.sql.sqltypes import AutoString

# ---------------------------------------------------------------------------
# Global configuration
# ---------------------------------------------------------------------------
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


# ---------------------------------------------------------------------------
# Autogenerate helpers
# ---------------------------------------------------------------------------
def _ensure_import(autogen_context: AutogenContext, import_stmt: str) -> None:
    """Ensure the given import is included in the generated migration."""
    imports = getattr(autogen_context, "imports", None)
    if imports is None:
        imports = set()
        autogen_context.imports = imports  # type: ignore[attr-defined]
    imports.add(import_stmt)


@renderers.dispatch_for(AutoString)
def _render_auto_string(type_: AutoString, autogen_context: AutogenContext) -> str:
    """Render SQLModel AutoString columns as sa.String."""
    _ensure_import(autogen_context, "import sqlalchemy as sa")
    _ensure_import(autogen_context, "import sqlmodel")
    length = getattr(type_, "length", None)
    return f"sa.String(length={length})" if length else "sa.String()"


@renderers.dispatch_for(Uuid)
def _render_uuid(type_: Uuid, autogen_context: AutogenContext) -> str:
    """Render SQLAlchemy's Uuid as sa.String(36) for cross-database support."""
    _ensure_import(autogen_context, "import sqlalchemy as sa")
    return "sa.String(length=36)"


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------
def get_url() -> str:
    """Resolve the database URL Alembic should target."""
    return settings.effective_database_url


# ---------------------------------------------------------------------------
# Migration entrypoints
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
