"""
Tag endpoints.
"""
import uuid
from typing import Annotated, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from sqlmodel import Session

from app.api.dependencies import get_current_user, get_plus_factory
from app.core.database import get_session
from app.core.exceptions import TagNotFoundError
from app.core.logging_config import log_error
from app.models.user import User
from app.plus import PLUS_MODE, PLUS_SERVICE_URL
from app.plus._proxy import _forward
from app.schemas.entry import EntryPreviewResponse
from app.schemas.media_thumbnail import MomentMediaThumbnail
from app.schemas.tag import (
    TagAnalyticsResponse,
    TagCreate,
    TagDetailAnalyticsResponse,
    TaggedMomentSummary,
    TagResponse,
    TagUpdate,
)
from app.services.media_service import MediaService
from app.services.tag_service import TagService

router = APIRouter(prefix="/tags", tags=["tags"])


# Tag CRUD Operations
@router.post(
    "/",
    response_model=TagResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Invalid tag data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    }
)
async def create_tag(
    tag_data: TagCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """Create a new tag."""
    tag_service = TagService(session)
    try:
        tag = tag_service.create_tag(current_user.id, tag_data)
        return tag
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from None
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating tag"
        ) from None


@router.get(
    "/",
    response_model=List[TagResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    }
)
async def get_user_tags(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None)
):
    """
    Get tags for the current user.

    Supports pagination and optional search filtering.
    """
    tag_service = TagService(session)
    tags = tag_service.get_user_tags(current_user.id, limit, offset, search)
    return tags


@router.get(
    "/popular",
    response_model=List[TagResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    }
)
async def get_popular_tags(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(20, ge=1, le=50)
):
    """
    Get most popular tags for the current user.

    Returns tags ordered by usage count (descending).
    """
    tag_service = TagService(session)
    tags = tag_service.get_popular_tags(current_user.id, limit)
    return tags


@router.get(
    "/search",
    response_model=List[TagResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    }
)
async def search_tags(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=50),
    include_unused: bool = Query(True),
):
    """Search tags by name."""
    tag_service = TagService(session)
    tags = tag_service.search_tags(
        current_user.id,
        q,
        limit=limit,
        include_unused=include_unused,
    )
    return tags


# Tag Analytics
@router.get(
    "/analytics",
    response_model=TagAnalyticsResponse,
    tags=["plus"],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Plus license required or invalid"},
        503: {"description": "Plus features not available in this build"},
        500: {"description": "Internal server error"},
    }
)
async def get_tag_analytics(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """
    Get detailed tag analytics.

    Returns detailed analytics with required time-series data (usage_over_time),
    tag distribution, and all statistics.

    **Requires:** Valid Journiv Plus license
    """
    try:
        if PLUS_MODE == "proxy":
            return await _forward(
                request,
                f"{PLUS_SERVICE_URL}/api/v1/plus/analytics/tags",
            )

        license_data = await get_plus_factory(current_user, session)
        tag_service = TagService(session)
        analytics = tag_service.get_tag_analytics(current_user.id, license_data)
        return analytics

    except PermissionError as e:
        # This should not happen since get_plus_factory already validates
        # But we catch it as defense in depth
        log_error(
            e,
            request_id="",
            user_email=current_user.email,
            extra_context=f"License verification failed in service layer: {e}"
        )
        raise HTTPException(
            status_code=403,
            detail={
                "error": "license_verification_failed",
                "message": f"License verification failed: {str(e)}",
                "action": "Please verify your license or contact support"
            }
        ) from None
    except RuntimeError as e:
        log_error(
            e,
            request_id="",
            user_email=current_user.email,
            extra_context=f"Plus analytics unavailable: {e}",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Plus analytics temporarily unavailable",
        ) from None
    except Exception as e:
        log_error(
            e,
            request_id="",
            user_email=current_user.email,
            extra_context=f"Error fetching tag analytics: {e}"
        )
        raise HTTPException(
            status_code=500,
            detail="An error occurred while fetching tag analytics"
        ) from None


@router.get(
    "/{tag_id}/analytics",
    response_model=TagDetailAnalyticsResponse,
    tags=["plus"],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Plus license required or invalid"},
        404: {"description": "Tag not found"},
        503: {"description": "Plus features not available in this build"},
        500: {"description": "Internal server error"},
    }
)
async def get_tag_detail_analytics(
    tag_id: uuid.UUID,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    days: Annotated[int, Query(ge=1, le=3650, description="Number of days to analyze")] = 365
):
    """
    Get detailed analytics for a specific tag.

    Returns trend analysis, peak month, growth rate, and usage over time
    for the specified tag.

    **Requires:** Valid Journiv Plus license
    """
    try:
        if PLUS_MODE == "proxy":
            return await _forward(
                request,
                f"{PLUS_SERVICE_URL}/api/v1/plus/analytics/tags/{tag_id}",
            )

        license_data = await get_plus_factory(current_user, session)
        tag_service = TagService(session)
        analytics = tag_service.get_tag_detail_analytics(
            tag_id=tag_id,
            user_id=current_user.id,
            license_data=license_data,
            days=days
        )
        return analytics

    except TagNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Tag not found"
        ) from None
    except PermissionError as e:
        # This should not happen since get_plus_factory already validates
        # But we catch it as defense in depth
        log_error(
            e,
            request_id="",
            user_email=current_user.email,
            extra_context=f"License verification failed in service layer: {e}"
        )
        raise HTTPException(
            status_code=403,
            detail={
                "error": "license_verification_failed",
                "message": f"License verification failed: {str(e)}",
                "action": "Please verify your license or contact support"
            }
        ) from None
    except RuntimeError as e:
        log_error(
            e,
            request_id="",
            user_email=current_user.email,
            extra_context=f"Plus tag detail analytics unavailable: {e}",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Plus analytics temporarily unavailable",
        ) from None
    except Exception as e:
        log_error(
            e,
            request_id="",
            user_email=current_user.email,
            extra_context=f"Error fetching tag detail analytics: {e}"
        )
        raise HTTPException(
            status_code=500,
            detail="An error occurred while fetching tag analytics"
        ) from None


@router.get(
    "/{tag_id}",
    response_model=TagResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Tag not found"},
    }
)
async def get_tag(
    tag_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """Get a specific tag by ID."""
    tag_service = TagService(session)
    try:
        tag = tag_service.get_tag_by_id(tag_id, current_user.id)
        if not tag:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tag not found"
            )
        return tag
    except HTTPException:
        raise
    except TagNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag not found"
        ) from None
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving tag"
        ) from None


@router.put(
    "/{tag_id}",
    response_model=TagResponse,
    responses={
        400: {"description": "Invalid tag data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Tag not found"},
        500: {"description": "Internal server error"},
    }
)
async def update_tag(
    tag_id: uuid.UUID,
    tag_data: TagUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """Update a tag."""
    tag_service = TagService(session)
    try:
        tag = tag_service.update_tag(tag_id, current_user.id, tag_data)
        return tag
    except TagNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag not found"
        ) from None
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from None
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating tag"
        ) from None


@router.delete(
    "/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Tag not found"},
        500: {"description": "Internal server error"},
    }
)
async def delete_tag(
    tag_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """Delete a tag."""
    tag_service = TagService(session)
    try:
        tag_service.delete_tag(tag_id, current_user.id)
    except TagNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag not found"
        ) from None
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting tag"
        ) from None


@router.post(
    "/{source_id}/merge/{target_id}",
    response_model=TagResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Invalid merge operation (e.g., merging into self)"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Source or target tag not found"},
        500: {"description": "Internal server error"},
    }
)
async def merge_tags(
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """
    Merge source tag into target tag.

    Moves all moment-tag links from source to target, then deletes source tag.
    Enforces case-normalization: prevents merging tags that differ only by case.
    """
    tag_service = TagService(session)
    try:
        # Prevent merging into self
        if source_id == target_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot merge tag into itself"
            )

        merged_tag = tag_service.merge_tags(source_id, target_id, current_user.id)
        return merged_tag
    except TagNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        ) from None
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from None
    except HTTPException:
        # Propagate deliberate HTTPExceptions (e.g., merging into self) unchanged
        raise
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while merging tags"
        ) from None


@router.get(
    "/{tag_id}/moments",
    response_model=List[TaggedMomentSummary],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Tag not found"},
    }
)
async def get_moments_by_tag(
    tag_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    include_media: Optional[str] = Query(None),
):
    """
    Get moments that have a specific tag.

    Returns moment summaries.
    """
    tag_service = TagService(session)
    try:
        if include_media not in (None, "thumbnails"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="include_media must be 'thumbnails' when provided",
            )

        moments = tag_service.get_moments_by_tag(tag_id, current_user.id, limit, offset)
        media_counts: dict[uuid.UUID, int] = {}
        media_map: dict[uuid.UUID, list] = {}
        if include_media == "thumbnails" and moments:
            media_service = MediaService(session)
            media_counts, media_map = media_service.get_moment_media_thumbnails(
                session,
                current_user.id,
                [moment.id for moment in moments],
            )
        return [
            TaggedMomentSummary(
                id=moment.id,
                logged_at_utc=moment.logged_at_utc,
                logged_date_tz=moment.logged_date_tz,
                entry=EntryPreviewResponse.model_validate(moment.entry) if moment.entry else None,
                note=moment.note,
                primary_mood_id=moment.primary_mood_id,
                media_count=media_counts.get(moment.id, moment.media_count),
                media=[
                    MomentMediaThumbnail(
                        id=thumb.id,
                        media_type=thumb.media_type,
                        signed_thumbnail_url=thumb.signed_thumbnail_url,
                    )
                    for thumb in media_map.get(moment.id, [])
                ],
            )
            for moment in moments
        ]
    except TagNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag not found"
        ) from None
