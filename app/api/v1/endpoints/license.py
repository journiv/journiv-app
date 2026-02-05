"""
License management API endpoints for Journiv Plus.
"""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session

from app.api.dependencies import get_current_admin_user, get_db
from app.core.exceptions import (
    LicenseResetEmailMismatchError,
    LicenseResetInstallIdMismatchError,
    LicenseResetRateLimitedError,
)
from app.core.logging_config import log_error, log_user_action
from app.models.user import User
from app.schemas.license import (
    LicenseInfoResponse,
    LicenseRegisterRequest,
    LicenseRegisterResponse,
    LicenseResetRequest,
    LicenseResetResponse,
)
from app.services.license_service import LicenseService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/instance/license", tags=["license"])


@router.post(
    "/register",
    response_model=LicenseRegisterResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Invalid license key format or validation failed"},
        401: {"description": "Not authenticated"},
        403: {"description": "Admin access required"},
        500: {"description": "Internal server error"},
    }
)
async def register_license(
    http_request: Request,
    request: LicenseRegisterRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_admin_user)]
) -> LicenseRegisterResponse:
    """
    Register a Plus license to this installation.

    Validates the license key with journiv-plus, binds it to this installation's
    install_id, and stores the encrypted license locally.
    """
    try:
        service = LicenseService(db)

        result = await service.register_license(
            license_key=request.license,
            email=request.email,
            discord_id=request.discord_id
        )

        if result.get("successful", False):
            log_user_action(
                current_user.email,
                "registered Plus license",
                request_id=getattr(http_request.state, 'request_id', None)
            )

        return LicenseRegisterResponse(
            successful=result.get("successful", False),
            signed_license=result.get("signed_license"),
            error_message=result.get("error_message")
        )

    except HTTPException:
        raise
    except Exception as e:
        log_error(
            e,
            request_id=getattr(http_request.state, 'request_id', None),
            user_email=current_user.email
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during license registration"
        ) from None


@router.get(
    "/info",
    response_model=LicenseInfoResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Admin access required"},
        404: {"description": "No license registered for this installation"},
        500: {"description": "Internal server error"},
        501: {"description": "Plus features module not available"},
        503: {"description": "Plus features module missing public key"},
    }
)
async def get_license_info(
    http_request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_admin_user)],
    refresh: bool = False,
) -> LicenseInfoResponse:
    """
    Get detailed information about the current Plus license.

    Returns license status, expiration date, registered email, and current tier.
    Set refresh=true to bypass cache and fetch fresh data from license server.
    """
    try:
        service = LicenseService(db)

        info = await service.get_license_info(refresh=refresh)

        if info is None:
            # No license registered - return 404 so frontend knows to show registration screen
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No license registered for this installation"
            )

        return LicenseInfoResponse(**info)

    except HTTPException:
        raise
    except Exception as e:
        log_error(
            e,
            request_id=getattr(http_request.state, 'request_id', None),
            user_email=current_user.email
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred retrieving license information"
        ) from None


@router.post(
    "/reset",
    response_model=LicenseResetResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Invalid request or install_id mismatch"},
        401: {"description": "Not authenticated"},
        403: {"description": "Email verification failed"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "Internal server error"},
    }
)
async def reset_license(
    http_request: Request,
    request: LicenseResetRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_admin_user)]
) -> LicenseResetResponse:
    """
    Unbind the Plus license from this installation.

    This operation:
    - Clears local license state (always, regardless of connectivity)
    - Attempts to unbind from journiv-plus server (best effort)
    - Is idempotent (safe to call multiple times)

    After unbinding, you can register the license on a different installation.
    Might require email verification (in future) to prevent unauthorized unbinding.

    Use cases:
    - Migrating to a new server
    - Reinstalling Journiv
    - Hardware changes that invalidate install_id
    """
    try:
        service = LicenseService(db)

        result = await service.reset_license(
            install_id=request.install_id,
            email=request.email
        )

        request_id = getattr(http_request.state, 'request_id', '')

        log_user_action(
            current_user.email,
            "unbound Plus license",
            request_id=request_id
        )

        # Log if upstream unbind had issues (for debugging)
        if result.get("error_message"):
            logger.warning(
                f"License unbind completed locally but upstream had issues: {result.get('error_message')}",
                extra={
                    "request_id": request_id or None,
                    "user_email": current_user.email,
                    "upstream_status": result.get("upstream_status")
                }
            )

        return LicenseResetResponse(status=result.get("status", "unknown"))

    except LicenseResetInstallIdMismatchError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="install_id does not match this installation"
        ) from None
    except LicenseResetEmailMismatchError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        ) from None
    except LicenseResetRateLimitedError as e:
        retry_after = e.retry_after
        wait_minutes = max(1, retry_after // 60)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limit_exceeded",
                "detail": f"Please wait {wait_minutes} minute(s) before resetting again",
                "retry_after": retry_after
            }
        ) from None
    except HTTPException:
        raise
    except Exception as e:
        log_error(
            e,
            request_id=getattr(http_request.state, 'request_id', None),
            user_email=current_user.email
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during license unbind"
        ) from None
