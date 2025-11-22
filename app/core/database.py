"""
Database configuration and session management with dual database support.
Supports SQLite (default) and PostgreSQL (optional override).
"""
import json
import logging
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine, Session, select

from app.core.config import settings, PROJECT_ROOT

logger = logging.getLogger(__name__)

# Get effective database URL and type
database_url = settings.effective_database_url
database_type = settings.database_type

# Sanitize database URL for logging using logging_config sanitization
from app.core.logging_config import _sanitize_data
safe_database_url = _sanitize_data(database_url)

logger.info(f"Using {database_type} database: {safe_database_url}")

# Database-specific engine configuration
if database_type == "sqlite":
    # SQLite-specific optimizations
    url = make_url(database_url)
    is_sqlite_memory = url.database in (None, "", ":memory:")

    engine_kwargs = {
        "echo": False,
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool if is_sqlite_memory else None,
    }

    engine = create_engine(database_url, **engine_kwargs)
    logger.info(f"Configured SQLite engine ({'in-memory' if is_sqlite_memory else 'file-based'})")

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        """Set SQLite-specific pragma settings for optimal performance."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        if not is_sqlite_memory:
            cursor.execute("PRAGMA journal_mode=WAL")  # Better concurrency
            cursor.execute("PRAGMA synchronous=NORMAL")  # Balance safety/performance
        cursor.execute("PRAGMA cache_size=10000")  # Increase cache
        cursor.execute("PRAGMA temp_store=MEMORY")  # Use memory for temp tables
        cursor.close()

elif database_type == "postgresql":
    # PostgreSQL-specific optimizations
    engine_kwargs = {
        "echo": False,
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 3,
        "pool_recycle": 3600,  # Recycle connections every hour
    }

    engine = create_engine(database_url, **engine_kwargs)
    logger.info("Configured PostgreSQL engine with connection pooling")

else:
    # Fallback for other database types
    engine_kwargs = {
        "echo": False,
        "pool_pre_ping": True,
    }
    engine = create_engine(database_url, **engine_kwargs)
    logger.warning(
        f"Using unsupported database type '{database_type}'. "
        "Install the appropriate DB driver for production use."
    )


def create_db_and_tables():
    """Create database tables using Alembic migrations."""
    import os

    # Skip migrations by default in production (migrations run by entrypoint script)
    # Set SKIP_DB_INIT=false to enable migrations in workers (e.g., for development)
    skip_db_init = os.getenv("SKIP_DB_INIT", "true").lower() in ("true", "1", "yes")
    if skip_db_init:
        logger.info("Skipping database initialization in worker (already performed by entrypoint script)")
        return

    try:
        # Run Alembic migrations using API instead of subprocess
        logger.info("Running database migrations...")
        from alembic import command
        from alembic.config import Config

        # Create Alembic config
        alembic_cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
        alembic_cfg.set_main_option("sqlalchemy.url", database_url)

        # Run migrations
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations completed successfully")

    except Exception as exc:
        logger.error(exc)
        # Fallback to SQLModel create_all
        try:
            logger.info("Falling back to SQLModel create_all...")
            SQLModel.metadata.create_all(engine)
            logger.info("Database tables created successfully (fallback)")
        except Exception as e:
            logger.error(e)
            raise


def get_session():
    """Get database session."""
    with Session(engine) as session:
        yield session


def seed_initial_data():
    """Seed initial data if database is empty."""
    import os

    # Skip data seeding by default in production (seeding run by entrypoint script)
    # Set SKIP_DATA_SEEDING=false to enable seeding in workers (e.g., for development)
    skip_data_seeding = os.getenv("SKIP_DATA_SEEDING", "true").lower() in ("true", "1", "yes")
    if skip_data_seeding:
        logger.info("Skipping data seeding in worker (already performed by entrypoint script)")
        return

    logger.info("Checking if initial data seeding is needed...")

    with Session(engine) as session:
        try:
            # Import models here to avoid circular imports
            from app.models.mood import Mood
            from app.models.prompt import Prompt

            # Check if moods exist
            existing_moods = session.exec(select(Mood)).first()
            if not existing_moods:
                logger.info("Seeding moods data...")
                seed_moods(session)
            else:
                logger.info("Moods already exist, skipping mood seeding")

            # Check if prompts exist
            existing_prompts = session.exec(select(Prompt)).first()
            if not existing_prompts:
                logger.info("Seeding prompts data...")
                seed_prompts(session)
            else:
                logger.info("Prompts already exist, skipping prompt seeding")

        except Exception as e:
            logger.error(e)
            # Don't raise the exception - seeding is not critical for app startup

def _seed_data_from_json(session: Session, model: type[SQLModel], file_path: Path, unique_field: str):
    """Generic function to seed data from a JSON file."""
    try:
        if not file_path.exists():
            logger.warning(f"Seed file not found: {file_path}")
            return

        with open(file_path, 'r', encoding='utf-8') as f:
            data_to_seed = json.load(f)

        # Fetch existing unique fields to avoid duplicates efficiently
        existing_items = session.exec(select(getattr(model, unique_field))).all()
        existing_set = set(existing_items)

        new_items_count = 0
        for item_data in data_to_seed:
            if item_data[unique_field] not in existing_set:
                session.add(model(**item_data))
                new_items_count += 1

        if new_items_count > 0:
            session.commit()
            logger.info(f"Seeded {new_items_count} new {model.__tablename__} successfully.")
        else:
            logger.info(f"All {model.__tablename__} already exist, no new items seeded.")

    except Exception as e:
        logger.error(e)
        session.rollback()


def seed_moods(session: Session):
    """Seed moods from JSON file."""
    from app.models.mood import Mood
    _seed_data_from_json(session, Mood, PROJECT_ROOT / "scripts/moods.json", "name")


def seed_prompts(session: Session):
    """Seed prompts from JSON file."""
    from app.models.prompt import Prompt
    _seed_data_from_json(session, Prompt, PROJECT_ROOT / "scripts/prompts.json", "text")


def init_db():
    """Initialize database with tables and seed data."""
    logger.info("Initializing database...")

    # Create tables
    create_db_and_tables()

    # Seed initial data
    seed_initial_data()

    logger.info("Database initialization completed")
