"""
FastAPI router for integration endpoints.

This module provides REST API endpoints for managing integrations with external
self-hosted services (Immich, Jellyfin, Audiobookshelf).

Endpoints:
- POST /integrations/connect: Connect a new integration
- GET /integrations/{provider}/status: Check connection status
- DELETE /integrations/{provider}/disconnect: Disconnect an integration
- GET /integrations/{provider}/assets: List assets from provider
- POST /integrations/{provider}/sync: Manually trigger sync

Authentication:
- All endpoints require valid JWT access token
- Users can only access their own integrations
"""
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Header
from starlette.background import BackgroundTask
from sqlmodel import Session, select

from app.core.database import get_session
from app.models.integration import Integration, IntegrationProvider  # Needed for proxy queries below.
from app.integrations.schemas import (
    IntegrationConnectRequest,
    IntegrationConnectResponse,
    IntegrationStatusResponse,
    IntegrationAssetsListResponse,
    IntegrationSettingsUpdateRequest,
)
from app.api.dependencies import get_current_user, get_current_user_detached
from app.core.config import settings
from app.core.scoped_cache import ScopedCache
from app.integrations.service import (
    connect_integration,
    get_integration_status,
    disconnect_integration,
    list_integration_assets,
    update_integration_settings,
)
from app.core.celery_app import celery_app
from app.models.user import User
from app.core.logging_config import log_info, log_error, log_warning
import httpx

router = APIRouter(prefix="/integrations", tags=["integrations"])


_proxy_client: Optional[httpx.AsyncClient] = None
_proxy_timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
_proxy_limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)


def _get_proxy_client() -> httpx.AsyncClient:
    """Reuse a single client to avoid connection churn under thumbnail bursts."""
    global _proxy_client
    if _proxy_client is None:
        _proxy_client = httpx.AsyncClient(
            verify=True,
            follow_redirects=True,
            timeout=_proxy_timeout,
            limits=_proxy_limits,
            transport=httpx.AsyncHTTPTransport(retries=2),
        )
    return _proxy_client


def _get_integration_cache() -> Optional[ScopedCache]:
    """Get the scoped cache for integration credentials."""
    if not settings.redis_url:
        return None
    return ScopedCache(namespace="integration_creds")


async def _close_httpx_stream(response: httpx.Response) -> None:
    """Ensure streamed HTTP responses release network resources."""
    await response.aclose()


@router.post(
    "/connect",
    response_model=IntegrationConnectResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Invalid provider or credentials"},
        401: {"description": "Not authenticated"},
        500: {"description": "Failed to connect to provider"},
    }
)
async def connect(
    request: IntegrationConnectRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
) -> IntegrationConnectResponse:
    """
    Connect or update an integration.

    Connect or update an integration with an external provider (e.g., Immich).
    Credentials are encrypted before storage.
    """
    try:
        response = await connect_integration(
            session=session,
            user=current_user,
            provider=request.provider,
            credentials=request.credentials,
            base_url=request.base_url,
            import_mode=request.import_mode
        )
        return response
    except ValueError as e:
        log_warning(f"Invalid integration connection request: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        log_error(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to connect to {request.provider}. Please check your credentials and try again."
        )


@router.get(
    "/{provider}/status",
    response_model=IntegrationStatusResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated"},
        500: {"description": "Failed to retrieve status"},
    }
)
async def get_status(
    provider: IntegrationProvider,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
) -> IntegrationStatusResponse:
    """
    Get the status of an integration.

    Returns the current connection status, sync history, and activity state.
    """
    try:
        status_response = await get_integration_status(
            session=session,
            user=current_user,
            provider=provider
        )
        return status_response
    except Exception as e:
        log_error(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve integration status"
        )


@router.delete(
    "/{provider}/disconnect",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Not authenticated"},
        404: {"description": "Integration not found"},
        500: {"description": "Failed to disconnect"},
    }
)
async def disconnect(
    provider: IntegrationProvider,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
) -> None:
    """
    Disconnect an integration.

    Deactivates the integration. Connection history and cached data are preserved.
    """
    try:
        await disconnect_integration(
            session=session,
            user=current_user,
            provider=provider
        )
        # Invalidate cache
        cache = _get_integration_cache()
        if cache:
            cache.delete(scope_id=current_user.id, cache_type=f"{provider.value}")
    except ValueError as e:
        log_warning(f"Integration not found for disconnect: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        log_error(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to disconnect integration"
        )


@router.put(
    "/{provider}/settings",
    response_model=IntegrationStatusResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated"},
        404: {"description": "Integration not found"},
        500: {"description": "Failed to update settings"},
    }
)
async def update_settings(
    provider: IntegrationProvider,
    request: IntegrationSettingsUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
) -> IntegrationStatusResponse:
    """
    Update integration settings.

    Updates settings like import mode without requiring reconnection.
    """
    try:
        status_response = await update_integration_settings(
            session=session,
            user=current_user,
            provider=provider,
            settings_update=request
        )
        return status_response
    except ValueError as e:
        log_warning(f"Integration not found for settings update: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        log_error(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update integration settings"
        )


@router.get(
    "/{provider}/assets",
    response_model=IntegrationAssetsListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Invalid request parameters"},
        401: {"description": "Not authenticated"},
        500: {"description": "Failed to retrieve assets"},
    }
)
async def list_assets(
    provider: IntegrationProvider,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    force_refresh: Annotated[bool, Query()] = False
) -> IntegrationAssetsListResponse:
    """
    List assets from a provider.

    Returns a paginated list of assets, using cached data when available.
    """
    try:

        assets, total_count = await list_integration_assets(
            session=session,
            user=current_user,
            provider=provider,
            page=page,
            limit=limit,
            force_refresh=force_refresh
        )

        # When total is unknown (-1), assume more if we got a full page
        if total_count == -1:
            has_more = len(assets) == limit
        else:
            has_more = len(assets) == limit and (total_count > (page * limit))

        return IntegrationAssetsListResponse(
            assets=assets,
            page=page,
            limit=limit,
            total=total_count,
            has_more=has_more
        )
    except ValueError as e:
        log_warning(f"Invalid asset list request: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        log_error(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve assets from {provider}"
        )


@router.post(
    "/{provider}/sync",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        400: {"description": "Integration not connected or disabled"},
        401: {"description": "Not authenticated"},
        500: {"description": "Failed to start sync"},
    }
)
async def trigger_sync(
    provider: IntegrationProvider,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
) -> dict:
    """
    Manually trigger a sync for an integration.

    Starts a background task to sync data from the provider.
    """
    try:
        # Verify integration exists and is active (quick check)
        status_response = await get_integration_status(
            session=session,
            user=current_user,
            provider=provider
        )

        if status_response.status == "disconnected":
            raise ValueError(f"{provider} is not connected")

        if status_response.status == "error":
            raise ValueError(f"{provider} integration in error state")

        if not status_response.is_active:
            raise ValueError(f"{provider} integration is disabled")

        # Schedule background task via Celery
        try:
            celery_app.send_task(
                "app.integrations.tasks.sync_provider_task",
                args=[str(current_user.id), provider.value]
            )
        except Exception as e:
            log_error(e, provider=provider, user_id=current_user.id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to start sync"
            )

        log_info(f"Scheduled sync for {provider} (user {current_user.id})")

        return {
            "status": "accepted",
            "message": f"Sync started for {provider}. Check status endpoint for results."
        }
    except ValueError as e:
        log_warning(f"Invalid sync request: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        log_error(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start sync"
        )


# ================================================================================
# PROXY ENDPOINTS
# ================================================================================

@router.get(
    "/{provider}/proxy/{asset_id}/thumbnail",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Integration not found or inactive"},
        401: {"description": "Not authenticated or provider authentication failed"},
        404: {"description": "Asset not found"},
        500: {"description": "Failed to fetch thumbnail"},
    }
)
async def proxy_thumbnail(
    provider: IntegrationProvider,
    asset_id: str,
    current_user: Annotated[User, Depends(get_current_user_detached)],
):
    """
    Proxy an asset's thumbnail from the provider.

    Proxies the thumbnail to the browser while handling authentication
    and caching.
    """
    from fastapi.responses import StreamingResponse
    from app.core.encryption import decrypt_token
    from app.core.database import get_session_context

    integration_base_url = None
    access_token_encrypted = None

    # 1. Try Cache First
    cache = _get_integration_cache()
    if cache:
        cached_creds = cache.get(scope_id=current_user.id, cache_type=f"{provider.value}")
        if cached_creds and cached_creds.get("is_active"):
            integration_base_url = cached_creds.get("base_url")
            access_token_encrypted = cached_creds.get("token")

    # 2. If not in cache, fetch from DB
    if not integration_base_url or not access_token_encrypted:
        with get_session_context() as session:
            # Get user's integration
            integration = session.exec(
                select(Integration)
                .where(Integration.user_id == current_user.id)
                .where(Integration.provider == provider)
            ).first()

            if not integration:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"{provider} integration not found. Please connect first."
                )

            if not integration.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"{provider} integration is disabled. Please reconnect."
                )

            # EXTRACT DATA eagerly before session closes
            integration_base_url = integration.base_url
            access_token_encrypted = integration.access_token_encrypted

        # 3. Populate Cache
        if cache:
            cache.set(
                scope_id=current_user.id,
                cache_type=f"{provider.value}",
                value={
                    "base_url": integration_base_url,
                    "token": access_token_encrypted,
                    "is_active": True
                },
                ttl_seconds=300 # Cache for 5 minutes
            )

    # Session is CLOSED here. Connection returned to pool.

    try:
        # Decrypt token
        api_key = decrypt_token(access_token_encrypted)

        # Build provider-specific thumbnail URL
        if provider == IntegrationProvider.IMMICH:
            # Validate asset_id to prevent path traversal
            import re
            if not re.match(r'^[a-zA-Z0-9_-]+$', asset_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid asset ID format"
                )
            thumbnail_url = f"{integration_base_url}/api/assets/{asset_id}/thumbnail"
        else:
            # Future: Add other providers
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=f"Thumbnail proxy not implemented for {provider}"
            )

        client = _get_proxy_client()
        try:
            request = client.build_request(
                "GET",
                thumbnail_url,
                headers={"x-api-key": api_key}
            )
            response = await client.send(request, stream=True)
        except Exception:
            raise

        # Handle provider errors
        if response.status_code in (401, 403):
            log_warning(f"Invalid {provider} token for user {current_user.id}")
            # We need a new session to update the error state since the main one is closed
            try:
                with get_session_context() as params_session:
                    # Re-fetch for update
                    integration_update = params_session.exec(
                         select(Integration)
                        .where(Integration.user_id == current_user.id)
                        .where(Integration.provider == provider)
                    ).first()
                    if integration_update:
                        integration_update.last_error = "Authentication failed"
                        integration_update.last_error_at = datetime.now(timezone.utc)
                        params_session.add(integration_update)
                        params_session.commit()
            except Exception as e:
                log_error(f"Failed to update integration error state: {e}")

            await _close_httpx_stream(response)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"{provider} authentication failed. Please reconnect your integration."
            )

        if response.status_code == 404:
            await _close_httpx_stream(response)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Asset {asset_id} not found in {provider}"
            )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            await _close_httpx_stream(response)
            detail = f"{provider} provider error"
            raise HTTPException(
                status_code=e.response.status_code,
                detail=detail
            )

        # Stream the thumbnail to the client without buffering entire file in memory
        return StreamingResponse(
            response.aiter_bytes(),
            media_type=response.headers.get("content-type", "image/jpeg"),
            headers={
                "Cache-Control": "public, max-age=3600",
                "X-Provider": provider.value
            },
            background=BackgroundTask(_close_httpx_stream, response)
        )

    except HTTPException:
        raise
    except Exception as e:
        log_error(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch thumbnail from {provider}"
        )


@router.get(
    "/{provider}/proxy/{asset_id}/original",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Integration not found or inactive"},
        401: {"description": "Not authenticated or provider authentication failed"},
        404: {"description": "Asset not found"},
        416: {"description": "Range not satisfiable"},
        500: {"description": "Failed to fetch original file"},
    }
)
async def proxy_original(
    provider: IntegrationProvider,
    asset_id: str,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user_detached)],
    range_header: Annotated[Optional[str], Header(alias="Range")] = None
):
    """
    Proxy an asset's original file from the provider.

    Supports Range requests for video streaming and seeking.
    """
    from fastapi.responses import StreamingResponse
    from app.core.encryption import decrypt_token
    from app.core.database import get_session_context

    integration_base_url = None
    access_token_encrypted = None

    try:
        # 1. Try Cache First
        cache = _get_integration_cache()
        if cache:
            cached_creds = cache.get(scope_id=current_user.id, cache_type=f"{provider.value}")
            if cached_creds and cached_creds.get("is_active"):
                integration_base_url = cached_creds.get("base_url")
                access_token_encrypted = cached_creds.get("token")

        # 2. If not in cache, fetch from DB
        if not integration_base_url or not access_token_encrypted:
            with get_session_context() as session:
                # Get user's integration
                integration = session.exec(
                    select(Integration)
                    .where(Integration.user_id == current_user.id)
                    .where(Integration.provider == provider)
                ).first()

                if not integration:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"{provider} integration not found. Please connect first."
                    )

                if not integration.is_active:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"{provider} integration is disabled. Please reconnect."
                    )

                # EXTRACT DATA eagerly before session closes
                integration_base_url = integration.base_url
                access_token_encrypted = integration.access_token_encrypted

            # 3. Populate Cache
            if cache:
                cache.set(
                    scope_id=current_user.id,
                    cache_type=f"{provider.value}",
                    value={
                        "base_url": integration_base_url,
                        "token": access_token_encrypted,
                        "is_active": True
                    },
                    ttl_seconds=300 # Cache for 5 minutes
                )

        # Session is CLOSED here. Connection returned to pool.

        # Decrypt token
        api_key = decrypt_token(access_token_encrypted)

        # Build provider-specific original URL
        if provider == IntegrationProvider.IMMICH:
            # Validate asset_id to prevent path traversal
            import re
            if not re.match(r'^[a-zA-Z0-9_-]+$', asset_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid asset ID format"
                )
            original_url = f"{integration_base_url}/api/assets/{asset_id}/original"
        else:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=f"Original proxy not implemented for {provider}"
            )

        # Prepare headers for Immich request
        headers = {"x-api-key": api_key}
        if range_header:
            headers["Range"] = range_header

        client = _get_proxy_client()
        try:
            proxied_request = client.build_request(
                "GET",
                original_url,
                headers=headers
            )
            response = await client.send(proxied_request, stream=True)
        except Exception:
            raise

        # Handle provider errors
        if response.status_code in (401, 403):
            log_warning(f"Invalid {provider} token for user {current_user.id}")

            # Update error state in new session
            try:
                with get_session_context() as params_session:
                    integration_update = params_session.exec(
                         select(Integration)
                        .where(Integration.user_id == current_user.id)
                        .where(Integration.provider == provider)
                    ).first()
                    if integration_update:
                        integration_update.last_error = "Authentication failed"
                        integration_update.last_error_at = datetime.now(timezone.utc)
                        params_session.add(integration_update)
                        params_session.commit()
            except Exception as e:
                log_error(f"Failed to update integration error state: {e}")

            await _close_httpx_stream(response)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"{provider} authentication failed. Please reconnect your integration."
            )

        if response.status_code == 404:
            await _close_httpx_stream(response)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Asset {asset_id} not found in {provider}"
            )

        if response.status_code == 416:
            await _close_httpx_stream(response)
            raise HTTPException(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                detail="Range Not Satisfiable"
            )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            await _close_httpx_stream(response)
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"{provider} provider error"
            )

        response_headers = {
            "Cache-Control": "public, max-age=3600",
            "X-Provider": provider.value,
        }

        if "content-range" in response.headers:
            response_headers["Content-Range"] = response.headers["content-range"]
        if "accept-ranges" in response.headers:
            response_headers["Accept-Ranges"] = response.headers["accept-ranges"]
        if "content-length" in response.headers:
            response_headers["Content-Length"] = response.headers["content-length"]

        status_code = (
            status.HTTP_206_PARTIAL_CONTENT
            if response.status_code == 206
            else status.HTTP_200_OK
        )

        return StreamingResponse(
            response.aiter_bytes(),
            status_code=status_code,
            media_type=response.headers.get("content-type", "application/octet-stream"),
            headers=response_headers,
            background=BackgroundTask(_close_httpx_stream, response)
        )

    except HTTPException:
        raise
    except Exception as e:
        log_error(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch original file from {provider}"
        )

# TODO Future: Add admin endpoint to trigger batch sync
# @router.post("/admin/sync-all")
# async def admin_sync_all(
#     current_user: Annotated[User, Depends(get_current_admin)],  # Requires admin role
#     background_tasks: BackgroundTasks
# ) -> dict:
#     """Trigger sync for all active integrations (admin only)"""
#     pass
