"""
Background tasks for integration synchronization.

This module provides an abstract interface for running integration sync tasks.
Uses Celery tasks for background execution and scheduling.

Architecture:
- sync_provider_task: Sync a specific provider for a user
- sync_all_providers_task: Sync all active integrations (scheduled job)
- Task wrapper: Handles database session management and error logging

Migration to Celery:
Scheduling:
    Use Celery Beat to run sync_all_providers_task on a fixed interval.
"""
import asyncio
from typing import Any, Awaitable, Callable

from sqlalchemy.pool import NullPool
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.celery_app import celery_app
from app.core.config import settings
from app.models.integration import IntegrationProvider
from app.integrations.service import (
    sync_integration,
    sync_all_integrations,
    add_assets_to_integration_album,
    remove_assets_from_integration_album
)
from app.models.user import User

from app.core.logging_config import log_info, log_error

def _build_async_database_url() -> str:
    url = make_url(settings.effective_database_url)
    if url.drivername.startswith("sqlite"):
        drivername = "sqlite+aiosqlite"
    elif url.drivername.startswith("postgres"):
        drivername = "postgresql+asyncpg"
    else:
        drivername = url.drivername
    return url.set(drivername=drivername).render_as_string(hide_password=False)


# Use NullPool to avoid sharing connections across different asyncio loops
# created by asyncio.run() in _run_async. Each task run gets a fresh connection.
async_engine = create_async_engine(
    _build_async_database_url(),
    echo=False,
    poolclass=NullPool
)
async_session_factory = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def _run_with_session(task_func: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
    async with async_session_factory() as session:
        return await task_func(session, *args, **kwargs)


def _run_async(task_func: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
    log_info(f"Starting background task: {task_func.__name__}")
    try:
        result = asyncio.run(_run_with_session(task_func, *args, **kwargs))
        log_info(f"Completed background task: {task_func.__name__}")
        return result
    except Exception as e:
        log_error(e, task_name=task_func.__name__)
        raise


async def _sync_provider_task(
    session: AsyncSession,
    user_id: str,
    provider: IntegrationProvider
) -> None:
    """
    Background task to sync a specific provider for a user.

    This task:
    1. Fetches the user's integration record
    2. Calls the provider's sync() function
    3. Updates last_synced_at and last_error fields
    """
    from sqlmodel import select

    # Get user
    user = (await session.exec(select(User).where(User.id == user_id))).first()
    if not user:
        error = Exception(f"User {user_id} not found for provider {provider}")
        log_error(error, provider=provider, user_id=user_id)
        return

    log_info(f"Syncing {provider} for user {user_id}")

    try:
        await sync_integration(session, user, provider)
        log_info(f"Successfully synced {provider} for user {user_id}")
    except Exception as e:
        log_error(e, provider=provider, user_id=user_id)
        # Error is already logged in integration.last_error by sync_integration
        # Don't re-raise to allow batch syncs to continue


async def _sync_all_providers_task(session: AsyncSession) -> None:
    """
    Background task to sync all active integrations across all users.

    This task:
    1. Queries all active integrations
    2. Syncs each one sequentially
    3. Logs overall progress
    4. Individual failures don't stop the batch

    Scheduling:
    - Manual trigger only (via admin API endpoint)
    - Schedule with Celery Beat every N hours
    """
    log_info("Starting scheduled sync for all active integrations")
    try:
        await sync_all_integrations(session)
        log_info("Completed scheduled sync for all integrations")
    except Exception as e:
        log_error(e)
        raise


@celery_app.task(name="app.integrations.tasks.sync_provider_task")
def sync_provider_task(user_id: str, provider: str) -> None:
    try:
        provider_enum = IntegrationProvider(provider)
    except ValueError as e:
        log_error(e, provider=provider, user_id=user_id)
        return

    _run_async(_sync_provider_task, user_id=user_id, provider=provider_enum)


@celery_app.task(name="app.integrations.tasks.sync_all_providers_task")
def sync_all_providers_task() -> None:
    _run_async(_sync_all_providers_task)


# ==============================================================================
# ALBUM MANAGEMENT TASKS
# ==============================================================================

async def _add_assets_to_album_task(
    session: AsyncSession,
    user_id: str,
    provider: IntegrationProvider,
    asset_ids: list[str]
) -> None:
    """Async worker for adding assets to album."""
    import uuid
    try:
        u_id = uuid.UUID(user_id)
        await add_assets_to_integration_album(session, u_id, provider, asset_ids)
    except Exception as e:
        log_error(e, user_id=user_id, message="Failed to add assets to album task")


@celery_app.task(name="app.integrations.tasks.add_assets_to_album_task")
def add_assets_to_album_task(user_id: str, provider: str, asset_ids: list[str]) -> None:
    """Celery task to add assets to provider album."""
    try:
        provider_enum = IntegrationProvider(provider)
        _run_async(_add_assets_to_album_task, user_id=user_id, provider=provider_enum, asset_ids=asset_ids)
    except ValueError as e:
        log_error(e, user_id=user_id, message="Invalid provider for album task")


async def _remove_assets_from_album_task(
    session: AsyncSession,
    user_id: str,
    provider: IntegrationProvider,
    asset_ids: list[str]
) -> None:
    """Async worker for removing assets from album."""
    import uuid
    try:
        u_id = uuid.UUID(user_id)
        await remove_assets_from_integration_album(session, u_id, provider, asset_ids)
    except Exception as e:
        log_error(e, user_id=user_id, message="Failed to remove assets from album task")


@celery_app.task(name="app.integrations.tasks.remove_assets_from_album_task")
def remove_assets_from_album_task(user_id: str, provider: str, asset_ids: list[str]) -> None:
    """Celery task to remove assets from provider album."""
    try:
        provider_enum = IntegrationProvider(provider)
        _run_async(_remove_assets_from_album_task, user_id=user_id, provider=provider_enum, asset_ids=asset_ids)
    except ValueError as e:
        log_error(e, user_id=user_id, message="Invalid provider for album task")
