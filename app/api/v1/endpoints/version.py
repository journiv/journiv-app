"""
Version checking endpoints.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.api.dependencies import get_current_admin_user
from app.core.database import get_session
from app.core.logging_config import log_info, log_warning
from app.models.user import User
from app.schemas.version import ForceVersionCheckResponse, VersionInfoResponse
from app.services.version_checker import VersionChecker, format_wait_time

router = APIRouter(prefix="/instance/version", tags=["version"])


class VersionCheckEnabledResponse(BaseModel):
    """Response for version check enabled status."""
    enabled: bool


class VersionCheckEnabledUpdate(BaseModel):
    """Request to update version check enabled status."""
    enabled: bool


@router.get(
    "/info",
    response_model=VersionInfoResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Admin access required"},
        500: {"description": "Internal server error"},
    }
)
async def get_version_info(
    current_user: Annotated[User, Depends(get_current_admin_user)],
    session: Annotated[Session, Depends(get_session)]
) -> VersionInfoResponse:
    """
    Get version information and update status.

    Returns cached information from the last version check without triggering a new check.
    """
    checker = VersionChecker(session)
    info = checker.get_version_info()

    if not info or not info.get("current_version") or not info.get("install_id"):
        log_warning("Version info unavailable or incomplete")
        raise HTTPException(
            status_code=500,
            detail="Version information is currently unavailable. Please try again later."
        )

    return VersionInfoResponse(**info)


@router.post(
    "/check",
    response_model=ForceVersionCheckResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Admin access required"},
        500: {"description": "Internal server error"},
    }
)
async def force_version_check(
    current_user: Annotated[User, Depends(get_current_admin_user)],
    session: Annotated[Session, Depends(get_session)]
) -> ForceVersionCheckResponse:
    """
    Force an immediate version check.

    Triggers a version check regardless of when the last check was performed.
    May be rate limited by Plus server (1 request per hour per instance).
    """
    log_info(f"User {current_user.id} triggered manual version check")

    checker = VersionChecker(session)
    result = await checker.check_for_updates(force=True)

    info = checker.get_version_info()

    # Handle rate limiting
    if result.get("rate_limited"):
        retry_after = result.get("retry_after_seconds", 3600)

        return ForceVersionCheckResponse(
            success=False,
            message=f"Rate limited. Please wait {format_wait_time(retry_after)} before checking again.",
            version_info=VersionInfoResponse(**info) if info.get("latest_version") else None,
            retry_after_seconds=retry_after
        )

    # Handle other errors (but still return cached info if available)
    if not result.get("success"):
        error_msg = result.get("error_message", "Unknown error")
        log_warning(f"Version check failed: {error_msg}")

        has_cached_data = bool(info.get("latest_version"))
        return ForceVersionCheckResponse(
            success=False,
            message=(
                "Using cached version info; latest check failed."
                if has_cached_data
                else "Version check failed. Please try again later."
            ),
            version_info=VersionInfoResponse(**info) if has_cached_data else None,
            retry_after_seconds=result.get("retry_after_seconds"),
            cached=has_cached_data
        )

    return ForceVersionCheckResponse(
        success=True,
        message="Version check completed successfully",
        version_info=VersionInfoResponse(**info),
        retry_after_seconds=None
    )


@router.get(
    "/check/enabled",
    response_model=VersionCheckEnabledResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Admin access required"},
        500: {"description": "Internal server error"},
    }
)
async def get_version_check_enabled(
    current_user: Annotated[User, Depends(get_current_admin_user)],
    session: Annotated[Session, Depends(get_session)]
) -> VersionCheckEnabledResponse:
    """
    Get whether version checking is enabled.

    Returns the current admin-controlled setting for version checking.
    """
    checker = VersionChecker(session)
    enabled = checker.get_version_check_enabled()
    log_info(f"User {current_user.email} checked version check enabled status: {enabled}")
    return VersionCheckEnabledResponse(enabled=enabled)


@router.put(
    "/check/enabled",
    response_model=VersionCheckEnabledResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Admin access required"},
        500: {"description": "Internal server error"},
    }
)
async def update_version_check_enabled(
    update: VersionCheckEnabledUpdate,
    current_user: Annotated[User, Depends(get_current_admin_user)],
    session: Annotated[Session, Depends(get_session)]
) -> VersionCheckEnabledResponse:
    """
    Update whether version checking is enabled.

    When enabling, triggers an immediate force version check so the user
    can see the latest version information right away.
    """
    checker = VersionChecker(session)
    enabled = checker.update_version_check_enabled(update.enabled)

    log_info(
        f"User {current_user.email} {'enabled' if update.enabled else 'disabled'} version checking"
    )

    if update.enabled:
        try:
            await checker.check_for_updates(force=True)
            log_info("Force version check completed after enabling version checking")
        except Exception as e:
            log_warning(f"Force version check failed after enabling: {e}")

    return VersionCheckEnabledResponse(enabled=enabled)
