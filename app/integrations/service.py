"""
Integration service layer and provider registry.

This module orchestrates integration operations across all providers.
It provides a unified interface for connecting, syncing, and querying integrations
regardless of the underlying provider.

Architecture:
- PROVIDER_REGISTRY: Maps provider enum → provider module
- Service functions: Handle business logic and database operations
- Provider modules: Handle provider-specific API calls

Design Principles:
- Thin service layer → delegate to provider modules
- Centralized error handling and logging
- Token encryption/decryption happens here
- Database operations use service pattern (not in providers)

Extension Points:
- Add new providers to PROVIDER_REGISTRY
- Providers must implement: connect(), list_assets(), sync()
- No changes to service.py required for new providers
"""
from inspect import isawaitable
import uuid
from typing import Optional, Dict, Any
import uuid

from pydantic import HttpUrl
from sqlmodel import Session, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.encryption import encrypt_token, decrypt_token
from app.core.time_utils import utc_now
from app.integrations import immich
from app.models.integration import Integration, IntegrationProvider, ImportMode, AssetType
from app.integrations.schemas import (
    IntegrationStatusResponse,
    IntegrationConnectResponse,
    IntegrationAssetResponse,
    IntegrationSettingsUpdateRequest,
)
from app.models.user import User

from app.core.logging_config import log_info, log_error, log_warning, log_debug
import httpx
import asyncio
from app.core.encryption import encrypt_token, decrypt_token
from app.core.scoped_cache import ScopedCache

_proxy_client: Optional[httpx.AsyncClient] = None
_proxy_lock = asyncio.Lock()
_proxy_timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
_proxy_limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)

# Shared cache instance (initialized once, reused for all calls)
_integration_cache: Optional[ScopedCache] = None


async def _get_proxy_client() -> httpx.AsyncClient:
    """Reuse a single client to avoid connection churn under thumbnail bursts."""
    global _proxy_client
    if _proxy_client is None:
        async with _proxy_lock:
            if _proxy_client is None:
                _proxy_client = httpx.AsyncClient(
                    verify=True,
                    follow_redirects=True,
                    timeout=_proxy_timeout,
                    limits=_proxy_limits,
                    transport=httpx.AsyncHTTPTransport(retries=2),
                )
    return _proxy_client


async def close_proxy_client() -> None:
    """
    Close the global proxy client to release network resources.

    This function should be called during application shutdown, typically from
    a FastAPI lifespan context manager or shutdown event handler.

    Example:
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            yield
            await close_proxy_client()
    """
    global _proxy_client
    if _proxy_client is not None:
        await _proxy_client.aclose()
        _proxy_client = None


def _get_integration_cache() -> Optional[ScopedCache]:
    """Get the scoped cache for integration credentials (singleton pattern)."""
    global _integration_cache
    if not settings.redis_url:
        return None
    if _integration_cache is None:
        _integration_cache = ScopedCache(namespace="integration_creds")
    return _integration_cache


def _set_integration_cache(
    user_id: uuid.UUID,
    provider: IntegrationProvider,
    *,
    base_url: str,
    token: str,
    is_active: bool,
    ttl_seconds: int = 300,
) -> None:
    cache = _get_integration_cache()
    if not cache:
        return
    cache.set(
        scope_id=str(user_id),
        cache_type=f"{provider.value}",
        value={"base_url": base_url, "token": token, "is_active": is_active},
        ttl_seconds=ttl_seconds,
    )


def _invalidate_integration_cache(user_id: uuid.UUID, provider: IntegrationProvider) -> None:
    cache = _get_integration_cache()
    if not cache:
        return
    cache.delete(scope_id=str(user_id), cache_type=f"{provider.value}")


# ================================================================================
# ASYNC COMPAT HELPERS
# ================================================================================

async def _exec(session: Session | AsyncSession, statement):
    result = session.exec(statement)
    if isawaitable(result):
        return await result
    return result


async def _commit(session: Session | AsyncSession) -> None:
    result = session.commit()
    if isawaitable(result):
        await result


async def _refresh(session: Session | AsyncSession, instance) -> None:
    result = session.refresh(instance)
    if isawaitable(result):
        await result


async def _rollback(session: Session | AsyncSession) -> None:
    result = session.rollback()
    if isawaitable(result):
        await result

# ================================================================================
# PROVIDER REGISTRY
# ================================================================================

# Maps IntegrationProvider enum → provider module
# Each module must implement: connect(), list_assets(), sync()
PROVIDER_REGISTRY = {
    IntegrationProvider.IMMICH: immich,
}


def get_provider_module(provider: IntegrationProvider):
    """
    Get the provider module for a given provider type.
    """
    module = PROVIDER_REGISTRY.get(provider)
    if not module:
        raise ValueError(
            f"Provider '{provider}' is not supported. "
            f"Supported providers: {list(PROVIDER_REGISTRY.keys())}"
        )
    return module


def get_default_base_url(provider: IntegrationProvider) -> Optional[str]:
    """
    Get the default base URL for a provider from environment variables.
    """
    # Only map providers that are actually defined in the IntegrationProvider enum
    env_var_map = {
        IntegrationProvider.IMMICH: settings.immich_base_url,
    }
    return env_var_map.get(provider)


# ================================================================================
# SERVICE FUNCTIONS
# ================================================================================

async def connect_integration(
    session: Session | AsyncSession,
    user: User,
    provider: IntegrationProvider,
    credentials: Dict[str, Any],
    base_url: Optional[HttpUrl] = None,
    import_mode: Optional[ImportMode] = None
) -> IntegrationConnectResponse:
    """
    Connect or update an integration for a user.

    Steps:
        1. Resolve base_url (use provided, or fall back to .env default)
        2. Validate credentials by calling provider's connect() function
        3. Encrypt and store access token
        4. Create or update Integration record
        5. Return connection response
    """
    # Resolve base URL
    final_base_url = str(base_url) if base_url else get_default_base_url(provider)
    if not final_base_url:
        raise ValueError(
            f"No base URL provided for {provider}. "
            f"Set {provider.value.upper()}_BASE_URL in .env or provide base_url in request."
        )

    # Normalize base URL (remove trailing slash)
    final_base_url = final_base_url.rstrip('/')

    # Get provider module and validate credentials
    provider_module = get_provider_module(provider)
    try:
        external_user_id = await provider_module.connect(
            session=session,
            user=user,
            base_url=final_base_url,
            credentials=credentials
        )
    except Exception as e:
        log_error(e, user_id=user.id)
        raise ValueError(f"Failed to connect to {provider}: {str(e)}")

    # Encrypt credentials for storage
    # Most providers use api_key, but support other auth types (future OAuth)
    access_token = credentials.get("api_key") or credentials.get("access_token")
    if not access_token:
        raise ValueError("Missing required credential: api_key or access_token")

    encrypted_token = encrypt_token(access_token)

    # Check if integration already exists (reconnection)
    existing = (await _exec(
        session,
        select(Integration)
        .where(Integration.user_id == user.id)
        .where(Integration.provider == provider)
    )).first()

    if existing:
        # Update existing integration
        existing.base_url = final_base_url
        existing.access_token_encrypted = encrypted_token
        existing.external_user_id = external_user_id
        existing.is_active = True
        existing.last_error = None
        existing.last_error_at = None
        if import_mode is not None:
            existing.import_mode = import_mode
        existing.updated_at = utc_now()
        session.add(existing)
        await _commit(session)
        await _refresh(session, existing)

        log_info(f"Reconnected {provider} for user {user.id} (integration {existing.id})")
        integration = existing
    else:
        # Create new integration
        integration = Integration(
            user_id=user.id,
            provider=provider,
            base_url=final_base_url,
            access_token_encrypted=encrypted_token,
            external_user_id=external_user_id,
            is_active=True,
            import_mode=import_mode or ImportMode.LINK_ONLY,
            connected_at=utc_now()
        )
        session.add(integration)
        await _commit(session)
        await _refresh(session, integration)

        log_info(f"Connected {provider} for user {user.id} (new integration {integration.id})")

    _set_integration_cache(
        user_id=user.id,
        provider=provider,
        base_url=integration.base_url,
        token=integration.access_token_encrypted,
        is_active=integration.is_active,
    )

    # Ensure setup (e.g., Album creation) for specific providers in link mode
    if provider == IntegrationProvider.IMMICH and integration.import_mode == ImportMode.LINK_ONLY:
        try:
            api_key = decrypt_token(integration.access_token_encrypted)
            album_id = await provider_module.ensure_album_exists(integration.base_url, api_key)

            if album_id:
                integration.update_metadata(album_id=album_id, album_error=None)
                session.add(integration)
                await _commit(session)
                await _refresh(session, integration)
                log_info(f"Created/found Immich album for user {user.id}: {album_id}")
            else:
                integration.update_metadata(album_id=None, album_error="Failed to create album")
                session.add(integration)
                await _commit(session)
                await _refresh(session, integration)
                log_warning(f"Could not create Immich album for user {user.id}")
        except Exception as e:
            # If metadata update fails, rollback and log warning but don't fail the connection
            error_msg = str(e)
            log_warning(e, user_id=user.id, message=f"Failed to save Immich album metadata: {error_msg}")
            try:
                await _rollback(session)
            except Exception:
                pass  # Rollback may fail if already rolled back

    _set_integration_cache(
        user_id=user.id,
        provider=provider,
        base_url=integration.base_url,
        token=integration.access_token_encrypted,
        is_active=integration.is_active,
    )

    return IntegrationConnectResponse(
        status="connected",
        provider=provider,
        external_user_id=external_user_id,
        connected_at=integration.connected_at
    )


async def get_integration_status(
    session: Session | AsyncSession,
    user: User,
    provider: IntegrationProvider
) -> IntegrationStatusResponse:
    """
    Get the current status of an integration.
    """
    integration = (await _exec(
        session,
        select(Integration)
        .where(Integration.user_id == user.id)
        .where(Integration.provider == provider)
    )).first()

    if not integration:
        # Not connected
        return IntegrationStatusResponse(
            provider=provider,
            status="disconnected",
            external_user_id=None,
            connected_at=None,
            last_synced_at=None,
            last_error=None,
            is_active=False,
            import_mode=ImportMode.LINK_ONLY,
            album_id=None,
            album_error=None
        )

    # Determine status
    if integration.last_error:
        status = "error"
    elif integration.is_active:
        status = "connected"
    else:
        status = "disconnected"

    # Extract album metadata
    metadata = integration.get_metadata()
    album_id = metadata.get("album_id")
    album_error = metadata.get("album_error")

    return IntegrationStatusResponse(
        provider=provider,
        status=status,
        external_user_id=integration.external_user_id,
        connected_at=integration.connected_at,
        last_synced_at=integration.last_synced_at,
        last_error=integration.last_error,
        is_active=integration.is_active,
        import_mode=integration.import_mode,
        album_id=album_id,
        album_error=album_error
    )


async def disconnect_integration(
    session: Session | AsyncSession,
    user: User,
    provider: IntegrationProvider
) -> None:
    """
    Disconnect an integration (soft delete).

    Sets is_active=False instead of deleting the record to preserve history.
    """
    integration = (await _exec(
        session,
        select(Integration)
        .where(Integration.user_id == user.id)
        .where(Integration.provider == provider)
    )).first()

    if not integration:
        raise ValueError(f"No {provider} integration found for user {user.id}")

    integration.is_active = False
    integration.updated_at = utc_now()
    session.add(integration)
    await _commit(session)

    log_info(f"Disconnected {provider} for user {user.id} (integration {integration.id})")

    # Invalidate cache
    _invalidate_integration_cache(user.id, provider)


async def list_integration_assets(
    session: Session | AsyncSession,
    user: User,
    provider: IntegrationProvider,
    page: int = 1,
    limit: int = 50,
    force_refresh: bool = False
) -> tuple[list[IntegrationAssetResponse], int]:
    """
    List assets from an integration provider.

    Returns:
        tuple: (assets list, total count). If total count is -1, it means the total is unknown.

    Strategy:
        1. Get user's integration record
        2. Delegate to provider's list_assets() function
        3. Provider decides whether to use cache or fetch live
    """
    # Get integration
    from app.core.database import get_session_context

    with get_session_context() as temp_session:
        integration = (await _exec(
            temp_session,
            select(Integration)
            .where(Integration.user_id == user.id)
            .where(Integration.provider == provider)
        )).first()
        if integration:
            temp_session.expunge(integration)

    if not integration:
        raise ValueError(f"No {provider} integration found. Please connect first.")

    if not integration.is_active:
        raise ValueError(f"{provider} integration is disabled. Please reconnect.")

    # Delegate to provider module
    provider_module = get_provider_module(provider)
    try:
        # Expected to return (assets, total)
        result = await provider_module.list_assets(
            session=session,
            user=user,
            integration=integration,
            page=page,
            limit=limit,
            force_refresh=force_refresh
        )

        # Handle if provider returns just list (backward compatibility or sloppy impl)
        if isinstance(result, tuple):
            return result
        return result, -1
    except Exception as e:
        log_error(e, user_id=user.id)
        # Update error tracking
        integration.last_error = str(e)
        integration.last_error_at = utc_now()
        session.add(integration)
        await _commit(session)
        raise


async def sync_integration(
    session: Session | AsyncSession,
    user: User,
    provider: IntegrationProvider
) -> None:
    """
    Manually trigger a sync for an integration.

    This is also called by scheduled background tasks.
    """
    # Get integration
    integration = (await _exec(
        session,
        select(Integration)
        .where(Integration.user_id == user.id)
        .where(Integration.provider == provider)
    )).first()

    if not integration:
        raise ValueError(f"No {provider} integration found")

    if not integration.is_active:
        log_info(f"Skipping sync for inactive {provider} integration (user {user.id})")
        return

    # Delegate to provider module
    provider_module = get_provider_module(provider)
    try:
        await provider_module.sync(
            session=session,
            user=user,
            integration=integration
        )

        # Update sync timestamp on success
        integration.last_synced_at = utc_now()
        integration.last_error = None
        integration.last_error_at = None
        session.add(integration)
        await _commit(session)

        log_info(f"Synced {provider} for user {user.id} (integration {integration.id})")
    except Exception as e:
        log_error(e, user_id=user.id)
        # Update error tracking
        integration.last_error = str(e)
        integration.last_error_at = utc_now()
        session.add(integration)
        await _commit(session)
        raise


async def sync_all_integrations(session: Session | AsyncSession) -> None:
    """
    Sync all active integrations across all users.

    This function is called by scheduled background tasks (e.g., every 6 hours).
    It iterates through all active integrations and syncs them.
    """
    integrations = (await _exec(
        session,
        select(Integration)
        .where(Integration.is_active == True)
    )).all()

    log_info(f"Starting batch sync for {len(integrations)} active integrations")

    for integration in integrations:
        try:
            # Get user (needed by provider modules)
            user = (await _exec(
                session,
                select(User).where(User.id == integration.user_id)
            )).first()

            if not user:
                log_warning(f"User {integration.user_id} not found for integration {integration.id}")
                continue

            await sync_integration(session, user, integration.provider)
        except Exception as e:
            log_error(
                e,
                integration_id=integration.id,
                provider=integration.provider,
                user_id=integration.user_id
            )
            # Continue with next integration (don't stop the batch)
            continue

    log_info(f"Completed batch sync for {len(integrations)} integrations")


async def update_integration_settings(
    session: Session | AsyncSession,
    user: User,
    provider: IntegrationProvider,
    settings_update: IntegrationSettingsUpdateRequest
) -> IntegrationStatusResponse:
    """
    Update integration settings without reconnecting.

    Currently supports updating import_mode and album_id.
    """
    integration = (await _exec(
        session,
        select(Integration)
        .where(Integration.user_id == user.id)
        .where(Integration.provider == provider)
    )).first()

    if not integration:
        raise ValueError(f"No {provider} integration found for user {user.id}")

    # Update import_mode if provided
    if settings_update.import_mode is not None:
        old_mode = integration.import_mode
        integration.import_mode = settings_update.import_mode
        integration.updated_at = utc_now()

        # Handle mode switching for Immich provider
        if provider == IntegrationProvider.IMMICH:
            # Switching from copy to link_only: ensure album exists
            if old_mode == ImportMode.COPY and settings_update.import_mode == ImportMode.LINK_ONLY:
                metadata = integration.get_metadata()
                existing_album_id = metadata.get("album_id")

                # If no album_id exists, try to create one
                if not existing_album_id:
                    try:
                        provider_module = get_provider_module(provider)
                        api_key = decrypt_token(integration.access_token_encrypted)
                        album_id = await provider_module.ensure_album_exists(integration.base_url, api_key)

                        if album_id:
                            integration.update_metadata(album_id=album_id, album_error=None)
                            log_info(f"Created Immich album on mode switch for user {user.id}: {album_id}")
                        else:
                            integration.update_metadata(album_error="Failed to create album")
                            log_warning(f"Could not create Immich album on mode switch for user {user.id}")
                    except Exception as e:
                        error_msg = str(e)
                        log_warning(e, user_id=user.id, message=f"Failed to create album on mode switch: {error_msg}")
                        integration.update_metadata(album_error=f"Album creation failed: {error_msg}")

        session.add(integration)
        await _commit(session)
        await _refresh(session, integration)

        log_info(
            f"Updated {provider} import_mode to {settings_update.import_mode} "
            f"for user {user.id} (integration {integration.id})"
        )
        _invalidate_integration_cache(user.id, provider)

    # Update album_id if provided (Immich only)
    if settings_update.album_id is not None and provider == IntegrationProvider.IMMICH:
        integration.update_metadata(album_id=settings_update.album_id, album_error=None)
        session.add(integration)
        await _commit(session)
        await _refresh(session, integration)

        log_info(
            f"Updated {provider} album_id to {settings_update.album_id} "
            f"for user {user.id} (integration {integration.id})"
        )
        _invalidate_integration_cache(user.id, provider)

    # Return updated status
    return await get_integration_status(session, user, provider)


async def get_integration_credentials(
    user_id: uuid.UUID,
    provider: IntegrationProvider,
) -> tuple[str, str]:
    """
    Retrieve integration credentials from cache or database.

    Returns a tuple of (base_url, encrypted_access_token).
    Database session is opened and closed immediately if cache misses.

    Raises:
        ValueError: If integration not found or disabled
    """
    # 1. Try cache first (avoid DB entirely if hit)
    cache = _get_integration_cache()
    if cache:
        cached_creds = cache.get(scope_id=str(user_id), cache_type=f"{provider.value}")
        if cached_creds and cached_creds.get("is_active"):
            base_url = cached_creds.get("base_url")
            encrypted_token = cached_creds.get("token")
            if base_url and encrypted_token:
                return base_url, encrypted_token

    # 2. Cache miss - fetch from DB with short-lived session
    from app.core.database import get_session_context
    with get_session_context() as session:
        integration = (await _exec(
            session,
            select(Integration)
            .where(Integration.user_id == user_id)
            .where(Integration.provider == provider)
        )).first()

        if not integration:
            raise ValueError(f"{provider} integration not found. Please connect first.")

        if not integration.is_active:
            raise ValueError(f"{provider} integration is disabled. Please reconnect.")

        base_url = integration.base_url
        encrypted_token = integration.access_token_encrypted
        # Session auto-closes here when exiting context

    # 3. Populate cache for next request
    if cache:
        cache.set(
            scope_id=str(user_id),
            cache_type=f"{provider.value}",
            value={
                "base_url": base_url,
                "token": encrypted_token,
                "is_active": True
            },
            ttl_seconds=300  # Cache for 5 minutes
        )

    return base_url, encrypted_token


async def fetch_proxy_asset(
    user_id: uuid.UUID,
    provider: IntegrationProvider,
    asset_id: str,
    variant: str,  # "thumbnail" or "original"
    range_header: Optional[str] = None,
) -> httpx.Response:
    """
    Fetch an asset stream from the provider.

    Handles credential retrieval (cache/DB), decryption, and request building.
    Returns the open httpx.Response object (headers unused).

    Database session is opened and closed internally during credential retrieval.
    No database connection is held during the HTTP request to the provider.

    IMPORTANT: The caller is responsible for ensuring the response is closed.
    You must call `response.aclose()` or stream the content fully.
    Failure to do so will leak connections.
    """
    # Get credentials (DB session opened and closed internally)
    integration_base_url, access_token_encrypted = await get_integration_credentials(
        user_id, provider
    )

    # Decrypt token
    try:
        api_key = decrypt_token(access_token_encrypted)
    except Exception as e:
        raise ValueError("Failed to decrypt integration credentials") from e

    # Build URL
    if provider == IntegrationProvider.IMMICH:
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', asset_id):
            raise ValueError("Invalid asset ID format")

        # Delegate URL construction to provider module
        # Resolve asset type (cache -> API) to correctly serve video vs image
        asset_type = AssetType.IMAGE
        if variant == "original":
            cached_type = immich.get_cached_asset_type(str(user_id), asset_id)
            if cached_type:
                asset_type = cached_type
            else:
                # Fetch detailed info if not in cache (avoids treating video as image)
                info = await immich.get_asset_info(integration_base_url, api_key, asset_id)
                if info.get("type") == "VIDEO":
                    asset_type = AssetType.VIDEO

        url = immich.get_asset_url(integration_base_url, asset_id, variant, asset_type)
    else:
        raise ValueError(f"Proxy not implemented for {provider}")

    # Prepare headers
    headers = {"x-api-key": api_key}
    if range_header and variant in ("thumbnail", "original"):
        headers["Range"] = range_header

    # Make request
    client = await _get_proxy_client()
    try:
        request = client.build_request("GET", url, headers=headers)
        # The timeout is already configured on the client itself at initialization
        response = await client.send(request, stream=True)
        return response
    except Exception as e:
        log_error(f"Proxy request failed: {e}", user_id=user_id)
        raise

async def add_assets_to_integration_album(
    session: Session | AsyncSession,
    user_id: uuid.UUID,
    provider: IntegrationProvider,
    asset_ids: list[str]
) -> None:
    """
    Add assets to the provider's specific album.

    For Immich in link_only mode, uses stored album_id from metadata.
    Skips if no album_id is present (e.g., album creation failed).
    """
    if not asset_ids:
        return

    # Get integration
    integration = (await _exec(
        session,
        select(Integration)
        .where(Integration.user_id == user_id)
        .where(Integration.provider == provider)
    )).first()

    if not integration or not integration.is_active:
        log_warning(f"Integration {provider} not active for user {user_id}, skipping album add")
        return

    # Only add to album in link_only mode
    if integration.import_mode != ImportMode.LINK_ONLY:
        log_debug(f"Integration {provider} is in copy mode, skipping album add")
        return

    provider_module = get_provider_module(provider)
    if not hasattr(provider_module, "add_assets_to_album"):
        log_warning(f"Provider {provider} does not support album addition")
        return

    # Get album_id from metadata
    metadata = integration.get_metadata()
    album_id = metadata.get("album_id")

    if not album_id:
        log_warning(
            f"No album_id found for {provider} integration (user {user_id}), skipping album add. "
            f"Album may not have been created due to permissions."
        )
        return

    try:
        api_key = decrypt_token(integration.access_token_encrypted)

        await provider_module.add_assets_to_album(
            integration.base_url,
            api_key,
            album_id,
            asset_ids
        )
        log_info(f"Added {len(asset_ids)} assets to {provider} album {album_id}")
    except Exception as e:
        log_error(e, user_id=user_id, message=f"Failed to add assets to {provider} album")
        # Don't raise, allowing background task to fail gracefully


async def remove_assets_from_integration_album(
    session: Session | AsyncSession,
    user_id: uuid.UUID,
    provider: IntegrationProvider,
    asset_ids: list[str]
) -> None:
    """
    Remove assets from the provider's specific album.
    """
    if not asset_ids:
        return

    # Filter out assets that are still in use by other entries for this user
    # This prevents removing an asset from the album if it's linked to multiple entries
    try:
        from app.models.entry import Entry, EntryMedia

        # Check if any of these assets are still referenced in the database
        # (The current entry's reference has already been deleted by this point)
        stmt = (
            select(EntryMedia.external_asset_id)
            .join(Entry)
            .where(
                Entry.user_id == user_id,
                EntryMedia.external_provider == provider.value,
                EntryMedia.external_asset_id.in_(asset_ids)
            )
        )

        result = await _exec(session, stmt)
        # Extract just the asset IDs from the query result (list of tuples)
        remaining_assets = {row[0] for row in result.all()}

        # Only remove assets that have no remaining references
        original_count = len(asset_ids)
        asset_ids = [aid for aid in asset_ids if aid not in remaining_assets]

        if not asset_ids:
            log_debug(f"All {original_count} assets are still in use by other entries, skipping removal from {provider} album")
            return

        if len(asset_ids) < original_count:
            log_debug(f"Partial removal: {len(asset_ids)}/{original_count} assets will be removed (others still in use)")

    except Exception as e:
        log_error(e, user_id=user_id, message="Failed to check asset usage before removal")
        return

    # Get integration
    integration = (await _exec(
        session,
        select(Integration)
        .where(Integration.user_id == user_id)
        .where(Integration.provider == provider)
    )).first()

    if not integration or not integration.is_active:
        return

    # Only remove from album in link_only mode
    if integration.import_mode != ImportMode.LINK_ONLY:
        return

    provider_module = get_provider_module(provider)
    if not hasattr(provider_module, "remove_assets_from_album"):
        return

    # Get album_id from metadata
    metadata = integration.get_metadata()
    album_id = metadata.get("album_id")

    if not album_id:
        log_warning(f"No album_id found for {provider} integration (user {user_id}), skipping asset removal")
        return

    try:
        api_key = decrypt_token(integration.access_token_encrypted)

        await provider_module.remove_assets_from_album(
            integration.base_url,
            api_key,
            album_id,
            asset_ids
        )
        log_info(f"Removed {len(asset_ids)} assets from {provider} album {album_id}")
    except Exception as e:
        log_error(e, user_id=user_id, message=f"Failed to remove assets from {provider} album")
