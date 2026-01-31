"""
Tag endpoints.
"""
import uuid
from typing import Annotated, List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlmodel import Session

from app.api.dependencies import get_current_user, get_plus_factory
from app.core.database import get_session
from app.core.exceptions import TagNotFoundError
from app.core.logging_config import log_error
from app.models.user import User
from app.schemas.entry import EntryPreviewResponse
from app.schemas.tag import TagCreate, TagUpdate, TagResponse, EntryTagLinkResponse, TagAnalyticsResponse, TagDetailAnalyticsResponse
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
        )
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating tag"
        )


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
    limit: int = Query(20, ge=1, le=50)
):
    """Search tags by name."""
    tag_service = TagService(session)
    tags = tag_service.search_tags(current_user.id, q, limit)
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
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    plus_factory=Depends(get_plus_factory)
):
    """
    Get detailed tag analytics.

    Returns detailed analytics with required time-series data (usage_over_time),
    tag distribution, and all statistics.

    **Requires:** Valid Journiv Plus license
    """
    try:
        tag_service = TagService(session)
        analytics = tag_service.get_tag_analytics(current_user.id, plus_factory)
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
        )
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
        )


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
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    plus_factory=Depends(get_plus_factory),
    days: int = Query(365, ge=1, le=3650, description="Number of days to analyze")
):
    """
    Get detailed analytics for a specific tag.

    Returns trend analysis, peak month, growth rate, and usage over time
    for the specified tag.

    **Requires:** Valid Journiv Plus license
    """
    try:
        tag_service = TagService(session)
        analytics = tag_service.get_tag_detail_analytics(
            tag_id=tag_id,
            user_id=current_user.id,
            plus_factory=plus_factory,
            days=days
        )
        return analytics

    except TagNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Tag not found"
        )
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
        )
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
        )


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
        )
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving tag"
        )


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
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating tag"
        )


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
        )
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting tag"
        )


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

    Moves all entry-tag links from source to target, then deletes source tag.
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
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        # Propagate deliberate HTTPExceptions (e.g., merging into self) unchanged
        raise
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while merging tags"
        )


# Entry-Tag Association Operations
@router.post(
    "/entry/{entry_id}/tag/{tag_id}",
    response_model=EntryTagLinkResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Tag or entry not found"},
        409: {"description": "Tag already associated with entry"},
        500: {"description": "Internal server error"},
    }
)
async def add_tag_to_entry(
    entry_id: uuid.UUID,
    tag_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """Add a tag to an entry."""
    tag_service = TagService(session)
    try:
        link = tag_service.add_tag_to_entry(entry_id, tag_id, current_user.id)
        return link
    except TagNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag not found"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while adding tag to entry"
        )


@router.delete(
    "/entry/{entry_id}/tag/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Tag or entry not found"},
        500: {"description": "Internal server error"},
    }
)
async def remove_tag_from_entry(
    entry_id: uuid.UUID,
    tag_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """Remove a tag from an entry."""
    tag_service = TagService(session)
    try:
        tag_service.remove_tag_from_entry(entry_id, tag_id, current_user.id)
    except TagNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag not found"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while removing tag from entry"
        )


@router.get(
    "/entry/{entry_id}",
    response_model=List[TagResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Entry not found"},
    }
)
async def get_entry_tags(
    entry_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """Get all tags for an entry."""
    tag_service = TagService(session)
    try:
        tags = tag_service.get_entry_tags(entry_id, current_user.id)
        return tags
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving entry tags"
        )


@router.post(
    "/entry/{entry_id}/bulk",
    response_model=List[TagResponse],
    responses={
        400: {"description": "Invalid tag names or empty list"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Entry not found"},
        500: {"description": "Internal server error"},
    }
)
async def bulk_add_tags_to_entry(
    entry_id: uuid.UUID,
    tag_names: List[str],
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """
    Add multiple tags to an entry by name.

    Creates tags if they don't exist. Ignores duplicates.
    """
    if not tag_names or len(tag_names) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tag names list cannot be empty"
        )

    tag_service = TagService(session)
    try:
        tags = tag_service.bulk_add_tags_to_entry(entry_id, tag_names, current_user.id)
        return tags
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while adding tags to entry"
        )


@router.get(
    "/{tag_id}/entries",
    response_model=List[EntryPreviewResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Tag not found"},
    }
)
async def get_entries_by_tag(
    tag_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    Get entries that have a specific tag.

    Returns entry previews with truncated content.
    """
    tag_service = TagService(session)
    try:
        entries = tag_service.get_entries_by_tag(tag_id, current_user.id, limit, offset)
        # Truncate content for preview
        return [
            EntryPreviewResponse(
                id=entry.id,
                title=entry.title or "Untitled",
                content_plain_text=(
                    entry.content_plain_text[:200] + "..."
                    if len(entry.content_plain_text or "") > 200
                    else entry.content_plain_text or ""
                ),
                journal_id=entry.journal_id,
                created_at=entry.created_at,
                updated_at=entry.updated_at,
                entry_date=entry.entry_date,
                entry_datetime_utc=entry.entry_datetime_utc,
                entry_timezone=entry.entry_timezone
            )
            for entry in entries
        ]
    except TagNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag not found"
        )
