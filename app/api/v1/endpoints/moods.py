"""
Mood endpoints.
"""
import uuid
from datetime import date
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.core.exceptions import (
    MoodAlreadyExistsError,
    MoodNotFoundError,
    ValidationError,
)
from app.core.logging_config import log_error
from app.models.user import User
from app.models.user_mood_preference import UserMoodPreference
from app.schemas.mood import (
    MoodCreate,
    MoodReorderRequest,
    MoodResponse,
    MoodUpdate,
    MoodVisibilityUpdate,
)
from app.schemas.mood_group import (
    MoodGroupCreate,
    MoodGroupMoodReorderRequest,
    MoodGroupReorderRequest,
    MoodGroupUpdate,
    MoodGroupVisibilityUpdate,
    MoodGroupWithMoodsResponse,
)
from app.services.mood_group_service import MoodGroupNotFoundError, MoodGroupService
from app.services.mood_service import MoodService

router = APIRouter(prefix="/moods", tags=["moods"])



@router.get(
    "/",
    response_model=List[MoodResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    },
)
async def get_all_moods(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    category: Optional[str] = Query(None),
    include_hidden: bool = Query(False),
):
    """
    Get moods visible to the current user, optionally filtered by category.

    Categories: positive, negative, neutral.
    """
    mood_service = MoodService(session)
    try:
        normalized_category = category.strip() if category else None

        if normalized_category and normalized_category not in ["positive", "negative", "neutral"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid category. Must be one of: positive, negative, neutral",
            )

        return mood_service.get_moods_for_user(
            current_user.id,
            normalized_category,
            include_hidden=include_hidden,
        )
    except HTTPException:
        raise
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving moods",
        ) from None


@router.post(
    "/",
    response_model=MoodResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Invalid input"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    },
)
async def create_mood(
    payload: MoodCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Create a user-defined mood."""
    mood_service = MoodService(session)
    try:
        mood = mood_service.create_user_mood(
            current_user.id,
            payload.model_dump(exclude_unset=True),
        )
        preference = session.exec(
            select(UserMoodPreference)
            .where(
                UserMoodPreference.user_id == current_user.id,
                UserMoodPreference.mood_id == mood.id,
            )
        ).first()
        return {
            **mood.model_dump(),
            "is_hidden": preference.is_hidden if preference else False,
            "sort_order": preference.sort_order if preference else None,
        }
    except (MoodAlreadyExistsError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating mood",
        ) from None


@router.put(
    "/reorder",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        400: {"description": "Invalid input"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    },
)
async def reorder_moods(
    payload: MoodReorderRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Reorder the unified mood list for the current user."""
    mood_service = MoodService(session)
    try:
        mood_service.reorder_moods(current_user.id, payload.mood_ids)
        return None
    except MoodNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while reordering moods",
        ) from None


@router.get(
    "/groups",
    response_model=List[MoodGroupWithMoodsResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    },
)
async def get_mood_groups(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    include_hidden: bool = Query(False),
):
    """Get all mood groups for the current user, including nested moods."""
    service = MoodGroupService(session)
    try:
        return service.get_groups_for_user(current_user.id, include_hidden=include_hidden)
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving mood groups",
        ) from None


@router.post(
    "/groups",
    response_model=MoodGroupWithMoodsResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Invalid group data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    },
)
async def create_mood_group(
    payload: MoodGroupCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    service = MoodGroupService(session)
    try:
        group = service.create_group(current_user.id, payload)
        return service.get_group_with_moods(
            current_user.id,
            group.id,
            include_hidden=True,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating mood group",
        ) from None


@router.put(
    "/groups/reorder",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    },
)
async def reorder_mood_groups(
    payload: MoodGroupReorderRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    service = MoodGroupService(session)
    updates = [(item.id, item.position) for item in payload.updates]
    try:
        service.reorder_groups(current_user.id, updates)
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while reordering mood groups",
        ) from None


@router.put(
    "/groups/{group_id}/visibility",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Mood group not found"},
    },
)
async def set_mood_group_visibility(
    group_id: uuid.UUID,
    payload: MoodGroupVisibilityUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    service = MoodGroupService(session)
    try:
        service.set_group_hidden(current_user.id, group_id, payload.is_hidden)
    except MoodGroupNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mood group not found",
        ) from None
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating mood group visibility",
        ) from None


@router.put(
    "/groups/{group_id}/moods/reorder",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Mood group not found"},
    },
)
async def reorder_mood_group_moods(
    group_id: uuid.UUID,
    payload: MoodGroupMoodReorderRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    service = MoodGroupService(session)
    try:
        service.reorder_group_moods(current_user.id, group_id, payload.mood_ids)
    except MoodGroupNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mood group not found",
        ) from None
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while reordering mood group moods",
        ) from None


@router.put(
    "/groups/{group_id}",
    response_model=MoodGroupWithMoodsResponse,
    responses={
        400: {"description": "Invalid group data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Mood group not found"},
    },
)
async def update_mood_group(
    group_id: uuid.UUID,
    payload: MoodGroupUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    service = MoodGroupService(session)
    try:
        group = service.update_group(group_id, current_user.id, payload)
        return service.get_group_with_moods(
            current_user.id,
            group.id,
            include_hidden=True,
        )
    except MoodGroupNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mood group not found",
        ) from None
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating mood group",
        ) from None


@router.delete(
    "/groups/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Mood group not found"},
    },
)
async def delete_mood_group(
    group_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    service = MoodGroupService(session)
    try:
        service.delete_group(group_id, current_user.id)
    except MoodGroupNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mood group not found",
        ) from None
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting mood group",
        ) from None


@router.get(
    "/analytics/statistics",
    response_model=Dict[str, Any],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    },
)
async def get_mood_statistics(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    start_date: Annotated[Optional[date], Query()] = None,
    end_date: Annotated[Optional[date], Query()] = None,
) -> Dict[str, Any]:
    """Get mood statistics for the current user."""
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must be before or equal to end_date",
        )
    mood_service = MoodService(session)
    try:
        return mood_service.get_mood_statistics(current_user.id, start_date, end_date)
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving mood statistics",
        ) from None


@router.get(
    "/analytics/streak",
    response_model=Dict[str, Any],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    },
)
async def get_mood_streak(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> Dict[str, Any]:
    """Get mood logging streak for the current user."""
    mood_service = MoodService(session)
    try:
        return mood_service.get_mood_streak(current_user.id)
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving mood streak",
        ) from None


@router.put(
    "/{mood_id}",
    response_model=MoodResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Mood not found"},
    },
)
async def update_mood(
    mood_id: uuid.UUID,
    payload: MoodUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Update a user-defined mood."""
    mood_service = MoodService(session)
    try:
        mood = mood_service.get_mood_by_id(mood_id)
        if not mood:
            raise HTTPException(status_code=404, detail="Mood not found")
        if mood.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Mood not found")
        mood = mood_service.update_user_mood(
            current_user.id,
            mood,
            payload.model_dump(exclude_unset=True),
        )
        preference = session.exec(
            select(UserMoodPreference)
            .where(
                UserMoodPreference.user_id == current_user.id,
                UserMoodPreference.mood_id == mood_id,
            )
        ).first()
        return {
            **mood.model_dump(),
            "is_hidden": preference.is_hidden if preference else False,
            "sort_order": preference.sort_order if preference else None,
        }
    except HTTPException:
        raise
    except (MoodAlreadyExistsError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating mood",
        ) from None


@router.get(
    "/{mood_id}",
    response_model=MoodResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Mood not found"},
    },
)
async def get_mood(
    mood_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Get a specific mood by ID."""
    mood_service = MoodService(session)
    try:
        mood = mood_service.get_mood_by_id(mood_id)
        if not mood:
            raise HTTPException(status_code=404, detail="Mood not found")
        if mood.user_id is not None and mood.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Mood not found")
        preference = session.exec(
            select(UserMoodPreference)
            .where(
                UserMoodPreference.user_id == current_user.id,
                UserMoodPreference.mood_id == mood_id,
            )
        ).first()
        return {
            **mood.model_dump(),
            "is_hidden": preference.is_hidden if preference else False,
            "sort_order": preference.sort_order if preference else None,
        }
    except HTTPException:
        raise
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving mood",
        ) from None


@router.delete(
    "/{mood_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Mood not found"},
    },
)
async def delete_mood(
    mood_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Soft delete a user-defined mood."""
    mood_service = MoodService(session)
    try:
        mood = mood_service.get_mood_by_id(mood_id)
        if not mood:
            raise HTTPException(status_code=404, detail="Mood not found")
        if mood.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Mood not found")
        mood_service.delete_user_mood(current_user.id, mood)
        return None
    except HTTPException:
        raise
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting mood",
        ) from None


@router.post(
    "/{mood_id}/visibility",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Mood not found"},
    },
)
async def update_mood_visibility(
    mood_id: uuid.UUID,
    payload: MoodVisibilityUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Hide/show a mood for the current user."""
    mood_service = MoodService(session)
    try:
        mood = mood_service.get_mood_by_id(mood_id)
        if not mood:
            raise HTTPException(status_code=404, detail="Mood not found")
        if mood.user_id is not None and mood.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Mood not found")
        mood_service.set_mood_hidden(current_user.id, mood_id, payload.is_hidden)
        return None
    except HTTPException:
        raise
    except MoodNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Mood not found") from exc
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating mood visibility",
        ) from None
