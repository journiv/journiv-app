"""
Instance configuration endpoints.
"""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.config import settings
from app.core.database import get_session
from app.core.plus_capability import get_plus_capability
from app.schemas.instance import InstanceConfigResponse

router = APIRouter(prefix="/instance", tags=["instance"])


@router.get(
    "/config",
    response_model=InstanceConfigResponse,
    summary="Get public instance configuration",
    responses={
        200: {"description": "Instance configuration retrieved successfully"},
        500: {"description": "Internal server error"},
    }
)
async def get_instance_config(
    session: Annotated[Session, Depends(get_session)],
) -> InstanceConfigResponse:
    """
    Get public instance configuration.

    Returns non-sensitive instance configuration settings for the frontend,
    including import/export file size limits, signup status, and this
    instance's Journiv Plus capability (see ``PlusCapability``).
    """
    return InstanceConfigResponse(
        import_export_max_file_size_mb=settings.import_export_max_file_size_mb,
        max_file_size_mb=settings.max_file_size_mb,
        allowed_media_types=settings.allowed_media_types,
        allowed_file_extensions=settings.allowed_file_extensions,
        disable_signup=settings.disable_signup,
        immich_base_url=settings.immich_base_url,
        oidc_enabled=settings.oidc_enabled,
        oidc_only=settings.oidc_only,
        plus=get_plus_capability(session),
    )
