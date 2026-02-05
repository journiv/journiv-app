"""
Mood endpoints.
"""
import uuid
from datetime import date
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.core.exceptions import EntryNotFoundError, MoodNotFoundError
from app.core.logging_config import log_error
from app.models.user import User
from app.schemas.mood import MoodLogCreate, MoodLogResponse, MoodLogUpdate, MoodResponse
from app.services.mood_service import MoodService

router = APIRouter(prefix="/moods", tags=["moods"])



# System Mood Management
@router.get(
    "/",
    response_model=List[MoodResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    }
)
async def get_all_moods(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    category: Annotated[Optional[str], Query()] = None
):
    """
    Get all system moods, optionally filtered by category.

    Categories: positive, negative, neutral.
    """
    mood_service = MoodService(session)
    try:
        # Normalize empty string to None
        normalized_category = category.strip() if category else None

        # Validate category if provided
        if normalized_category and normalized_category not in ["positive", "negative", "neutral"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid category. Must be one of: positive, negative, neutral"
            )

        if normalized_category:
            moods = mood_service.get_moods_by_category(normalized_category)
        else:
            moods = mood_service.get_all_moods()
        return moods
    except HTTPException:
        raise
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving moods"
        ) from None


@router.get(
    "/logs",
    response_model=List[MoodLogResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    }
)
async def get_user_mood_logs(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    mood_id: Annotated[Optional[str], Query()] = None,
    entry_id: Annotated[Optional[str], Query()] = None,
    start_date: Annotated[Optional[str], Query()] = None,
    end_date: Annotated[Optional[str], Query()] = None
):
    """
    Get mood logs for the current user with optional filters.

    Supports filtering by mood, entry, and date range with pagination.
    """
    mood_service = MoodService(session)
    try:
        # Parse optional parameters that might be sent as empty strings
        parsed_mood_id: Optional[uuid.UUID] = None
        if mood_id and mood_id.strip():
            try:
                parsed_mood_id = uuid.UUID(mood_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid mood_id format"
                ) from None

        parsed_entry_id: Optional[uuid.UUID] = None
        if entry_id and entry_id.strip():
            try:
                parsed_entry_id = uuid.UUID(entry_id)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid entry_id format"
                ) from None

        parsed_start_date: Optional[date] = None
        if start_date and start_date.strip():
            try:
                parsed_start_date = date.fromisoformat(start_date)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid start_date format (YYYY-MM-DD)"
                ) from None

        parsed_end_date: Optional[date] = None
        if end_date and end_date.strip():
            try:
                parsed_end_date = date.fromisoformat(end_date)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid end_date format (YYYY-MM-DD)"
                ) from None

        mood_logs = mood_service.get_user_mood_logs(
            current_user.id, limit, offset, parsed_mood_id, parsed_entry_id, parsed_start_date, parsed_end_date
        )
        return mood_logs
    except HTTPException:
        raise
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving mood logs"
        ) from None


# User Mood Logging - IMPORTANT: /log/recent must come BEFORE /log/{mood_log_id}
@router.get(
    "/log/recent",
    response_model=List[MoodLogResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    }
)
async def get_recent_moods(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10
):
    """
    Get recent mood logs for the current user.

    Returns most recent mood logs ordered by logged_at timestamp (descending).
    """
    mood_service = MoodService(session)
    try:
        mood_logs = mood_service.get_recent_moods(current_user.id, limit)
        return mood_logs
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving recent moods"
        ) from None


@router.post(
    "/log",
    response_model=MoodLogResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Invalid mood log data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Mood or entry not found"},
    }
)
async def log_mood(
    mood_log_data: MoodLogCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """Log a mood for the current user."""
    mood_service = MoodService(session)
    try:
        mood_log = mood_service.log_mood(current_user.id, mood_log_data)
        return mood_log
    except MoodNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mood not found"
        ) from None
    except EntryNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found"
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
            detail="An error occurred while logging mood"
        ) from None


@router.get(
    "/log/{mood_log_id}",
    response_model=MoodLogResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Mood log not found"},
    }
)
async def get_mood_log(
    mood_log_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """Get a specific mood log by ID."""
    mood_service = MoodService(session)
    try:
        mood_log = mood_service.get_mood_log_by_id(mood_log_id, current_user.id)
        if not mood_log:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mood log not found"
            )
        return mood_log
    except HTTPException:
        raise
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving mood log"
        ) from None


@router.put(
    "/log/{mood_log_id}",
    response_model=MoodLogResponse,
    responses={
        400: {"description": "Invalid mood log data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Mood log not found"},
    }
)
async def update_mood_log(
    mood_log_id: uuid.UUID,
    mood_log_data: MoodLogUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """Update a mood log."""
    mood_service = MoodService(session)
    try:
        mood_log = mood_service.update_mood_log(mood_log_id, current_user.id, mood_log_data)
        return mood_log
    except MoodNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mood log not found"
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
            detail="An error occurred while updating mood log"
        ) from None


@router.delete(
    "/log/{mood_log_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Mood log not found"},
    }
)
async def delete_mood_log(
    mood_log_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """Delete a mood log."""
    mood_service = MoodService(session)
    try:
        mood_service.delete_mood_log(mood_log_id, current_user.id)
    except MoodNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mood log not found"
        ) from None
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting mood log"
        ) from None


# Mood Analytics
@router.get(
    "/analytics/statistics",
    response_model=Dict[str, Any],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    }
)
async def get_mood_statistics(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    start_date: Annotated[Optional[date], Query()] = None,
    end_date: Annotated[Optional[date], Query()] = None
):
    """
    Get mood statistics for the current user.

    Includes mood distribution, trends, and patterns over the specified date range.
    """
    mood_service = MoodService(session)
    try:
        statistics = mood_service.get_mood_statistics(current_user.id, start_date, end_date)
        return statistics
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving mood statistics"
        ) from None


@router.get(
    "/analytics/streak",
    response_model=Dict[str, Any],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    }
)
async def get_mood_streak(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """
    Get mood logging streak for the current user.

    Tracks consecutive days with mood logging activity.
    """
    mood_service = MoodService(session)
    try:
        streak = mood_service.get_mood_streak(current_user.id)
        return streak
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving mood streak"
        ) from None


@router.get(
    "/{mood_id}",
    response_model=MoodResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Mood not found"},
    }
)
async def get_mood(
    mood_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """Get a specific mood by ID."""
    mood_service = MoodService(session)
    try:
        mood = mood_service.get_mood_by_id(mood_id)
        if not mood:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mood not found"
            )
        return mood
    except HTTPException:
        raise
    except MoodNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mood not found"
        ) from None
    except Exception as e:
        log_error(e, request_id="", user_email=current_user.email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while retrieving mood"
        ) from None
