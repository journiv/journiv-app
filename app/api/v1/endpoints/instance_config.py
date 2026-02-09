"""
Instance configuration endpoints.
"""
from fastapi import APIRouter

from app.core.config import settings
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
async def get_instance_config() -> InstanceConfigResponse:
    """
    Get public instance configuration.

    Returns non-sensitive instance configuration settings for the frontend,
    including import/export file size limits and signup status.
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
    )
