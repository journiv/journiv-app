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
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from starlette.background import BackgroundTask
from sqlmodel import Session, select

from app.core.database import get_session, get_session_context
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
from app.core.media_signing import is_signature_expired
from app.core.signing import verify_media_signature
from app.integrations.service import (
    connect_integration,
    get_integration_status,
    disconnect_integration,
    list_integration_assets,
    update_integration_settings,
    fetch_proxy_asset,
)
from app.core.celery_app import celery_app
from app.models.user import User
from app.core.logging_config import log_info, log_error, log_warning
import httpx

router = APIRouter(prefix="/integrations", tags=["integrations"])



async def _close_httpx_stream(response: httpx.Response) -> None:
    """Ensure streamed HTTP responses release network resources."""
    await response.aclose()


async def _update_integration_error_state(
    user_id: uuid.UUID,
    provider: IntegrationProvider,
    error_message: str
) -> None:
    """
    Update integration error state in a new database session.

    Used when proxy requests fail due to authentication errors.
    Creates a short-lived session to record the error without blocking.
    """
    try:
        with get_session_context() as session:
            integration_update = session.exec(
                select(Integration)
                .where(Integration.user_id == user_id)
                .where(Integration.provider == provider)
            ).first()
            if integration_update:
                integration_update.last_error = error_message
                integration_update.last_error_at = datetime.now(timezone.utc)
                session.add(integration_update)
                session.commit()
    except Exception as e:  # noqa: BLE001 - Broad except intentional to ensure best-effort error reporting
        log_error(e, message="Failed to update integration error state")


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
    current_user: Annotated[User, Depends(get_current_user_detached)],
) -> IntegrationConnectResponse:
    """
    Connect or update an integration.

    Connect or update an integration with an external provider (e.g., Immich).
    Credentials are encrypted before storage.
    """
    try:
        with get_session_context() as session:
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
    current_user: Annotated[User, Depends(get_current_user_detached)],
) -> IntegrationStatusResponse:
    """
    Get the status of an integration.

    Returns the current connection status, sync history, and activity state.
    """
    try:
        with get_session_context() as session:
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
    current_user: Annotated[User, Depends(get_current_user_detached)],
) -> None:
    """
    Disconnect an integration.

    Deactivates the integration. Connection history and cached data are preserved.
    """
    try:
        with get_session_context() as session:
            await disconnect_integration(
                session=session,
                user=current_user,
                provider=provider
            )
        # Cache invalidation is handled in the service
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
    current_user: Annotated[User, Depends(get_current_user_detached)],
) -> IntegrationStatusResponse:
    """
    Update integration settings.

    Updates settings like import mode without requiring reconnection.
    """
    try:
        with get_session_context() as session:
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
    current_user: Annotated[User, Depends(get_current_user_detached)],
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    force_refresh: Annotated[bool, Query()] = False
) -> IntegrationAssetsListResponse:
    """
    List assets from a provider.

    Returns a paginated list of assets, using cached data when available.
    """
    try:
        with get_session_context() as session:
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
    current_user: Annotated[User, Depends(get_current_user_detached)],
) -> dict:
    """
    Manually trigger a sync for an integration.

    Starts a background task to sync data from the provider.
    """
    try:
        # Verify integration exists and is active (quick check)
        with get_session_context() as session:
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
    uid: Annotated[str, Query(alias="uid")],
    exp: Annotated[int, Query(alias="exp")],
    sig: Annotated[str, Query(alias="sig")],
):
    """
    Proxy an asset's thumbnail from the provider.

    Proxies the thumbnail to the browser while handling authentication
    and caching.
    """
    from fastapi.responses import StreamingResponse

    try:
        user_id = uuid.UUID(uid)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")
    if is_signature_expired(exp, settings.media_signed_url_grace_seconds):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Signed URL expired")
    if not verify_media_signature(
        provider.value,
        "thumbnail",
        asset_id,
        str(user_id),
        exp,
        sig,
        settings.secret_key,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")

    # 1. Fetch asset stream using service
    # Database session is managed internally by fetch_proxy_asset during credential retrieval
    # and closed before the HTTP streaming begins to prevent connection leaks
    try:
        response = await fetch_proxy_asset(
            user_id=user_id,
            provider=provider,
            asset_id=asset_id,
            variant="thumbnail",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        log_error(f"Proxy thumbnail failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch thumbnail")

    # Handle provider errors
    if response.status_code in (401, 403):
        log_warning(f"Invalid {provider} token for user {user_id}")
        await _update_integration_error_state(user_id, provider, "Authentication failed")
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
    uid: Annotated[str, Query(alias="uid")],
    exp: Annotated[int, Query(alias="exp")],
    sig: Annotated[str, Query(alias="sig")],
    range_header: Annotated[Optional[str], Header(alias="Range")] = None
):
    """
    Proxy an asset's original file from the provider.

    Supports Range requests for video streaming and seeking.
    """
    from fastapi.responses import StreamingResponse

    try:
        user_id = uuid.UUID(uid)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")
    if is_signature_expired(exp, settings.media_signed_url_grace_seconds):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Signed URL expired")
    if not verify_media_signature(
        provider.value,
        "original",
        asset_id,
        str(user_id),
        exp,
        sig,
        settings.secret_key,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")

    # 1. Fetch asset stream using service
    # Database session is managed internally by fetch_proxy_asset during credential retrieval
    # and closed before the HTTP streaming begins to prevent connection leaks
    try:
        response = await fetch_proxy_asset(
            user_id=user_id,
            provider=provider,
            asset_id=asset_id,
            variant="original",
            range_header=range_header,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        log_error(f"Proxy original failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch original file",
        )

    # Handle provider errors
    if response.status_code in (401, 403):
        log_warning(f"Invalid {provider} token for user {user_id}")
        await _update_integration_error_state(user_id, provider, "Authentication failed")
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



# TODO Future: Add admin endpoint to trigger batch sync
# @router.post("/admin/sync-all")
# async def admin_sync_all(
#     current_user: Annotated[User, Depends(get_current_admin)],  # Requires admin role
#     background_tasks: BackgroundTasks
# ) -> dict:
#     """Trigger sync for all active integrations (admin only)"""
#     pass
