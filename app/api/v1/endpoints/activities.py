"""
Activity endpoints.
"""
import uuid
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.core.logging_config import log_error
from app.models.user import User
from app.schemas.activity import (
    ActivityCreate,
    ActivityReorderRequest,
    ActivityResponse,
    ActivityUpdate,
    ActivityWithUsageResponse,
)
from app.services.activity_service import ActivityNotFoundError, ActivityService

router = APIRouter(prefix="/activities", tags=["activities"])


@router.get(
    "",
    response_model=List[ActivityResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    },
)
async def get_activities(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None),
):
    """Get all activities for the current user."""
    activity_service = ActivityService(session)
    return activity_service.get_user_activities(current_user.id, limit, offset, search)


@router.post(
    "",
    response_model=ActivityResponse,
    responses={
        400: {"description": "Invalid activity data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    },
)
async def create_activity(
    activity_data: ActivityCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Create a new activity."""
    activity_service = ActivityService(session)
    try:
        return activity_service.create_activity(current_user.id, activity_data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while creating activity",
        ) from exc


@router.put(
    "/reorder",
    status_code=204,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    },
)
async def reorder_activities(
    reorder_data: ActivityReorderRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Reorder activities for the current user."""
    activity_service = ActivityService(session)
    updates = [(item.id, item.position) for item in reorder_data.updates]
    try:
        activity_service.reorder_activities(current_user.id, updates)
    except ActivityNotFoundError as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=404,
            detail="Activity not found or not owned by user",
        ) from None
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while reordering activities",
        ) from exc


@router.get(
    "/{activity_id}",
    response_model=ActivityWithUsageResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Activity not found"},
    },
)
async def get_activity(
    activity_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Get a specific activity and usage count."""
    activity_service = ActivityService(session)
    activity = activity_service.get_activity_by_id(activity_id, current_user.id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    usage_count = activity_service.get_activity_usage_count(activity_id, current_user.id)
    return ActivityWithUsageResponse(
        **activity.model_dump(),
        usage_count=usage_count,
    )


@router.put(
    "/{activity_id}",
    response_model=ActivityResponse,
    responses={
        400: {"description": "Invalid activity data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Activity not found"},
    },
)
async def update_activity(
    activity_id: uuid.UUID,
    activity_data: ActivityUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Update an activity."""
    activity_service = ActivityService(session)
    try:
        return activity_service.update_activity(activity_id, current_user.id, activity_data)
    except ActivityNotFoundError:
        raise HTTPException(status_code=404, detail="Activity not found") from None
    except ValueError as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(status_code=400, detail="Invalid activity data") from exc
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while updating activity",
        ) from exc


@router.delete(
    "/{activity_id}",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Activity not found"},
    },
)
async def delete_activity(
    activity_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Delete an activity."""
    activity_service = ActivityService(session)
    try:
        activity_service.delete_activity(activity_id, current_user.id)
        return {"status": "deleted"}
    except ActivityNotFoundError:
        raise HTTPException(status_code=404, detail="Activity not found") from None
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while deleting activity",
        ) from exc
