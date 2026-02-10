"""
Activity Group management endpoints.
"""
import uuid
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.core.logging_config import log_error
from app.models.user import User
from app.schemas.activity_group import (
    ActivityGroupCreate,
    ActivityGroupReorderRequest,
    ActivityGroupResponse,
    ActivityGroupUpdate,
    ActivityGroupWithActivitiesResponse,
)
from app.services.activity_group_service import (
    ActivityGroupNotFoundError,
    ActivityGroupService,
)

router = APIRouter(prefix="/activity-groups", tags=["activity-groups"])



@router.post(
    "/",
    response_model=ActivityGroupResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Invalid group data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    }
)
async def create_activity_group(
    group_data: ActivityGroupCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Create a new activity group."""
    service = ActivityGroupService(session)
    try:
        group = service.create_group(current_user.id, group_data)
        return group
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) from e
    except Exception as e:
        log_error(e, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating activity group"
        ) from e


@router.get(
    "/",
    response_model=List[ActivityGroupWithActivitiesResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    }
)
async def get_activity_groups(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """
    Get all activity groups for the current user, including their activities.
    """
    service = ActivityGroupService(session)
    groups = service.get_user_groups(current_user.id)
    return groups


@router.get(
    "/{group_id}",
    response_model=ActivityGroupWithActivitiesResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Group not found"},
    }
)
async def get_activity_group(
    group_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """Get a specific activity group."""
    service = ActivityGroupService(session)
    group = service.get_group_by_id(group_id, current_user.id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity group not found"
        )
    return group


@router.put(
    "/reorder",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    }
)
async def reorder_activity_groups(
    reorder_data: ActivityGroupReorderRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Reorder activity groups for the current user."""
    service = ActivityGroupService(session)
    updates = [(item.id, item.position) for item in reorder_data.updates]
    try:
        service.reorder_groups(current_user.id, updates)
    except Exception as e:
        log_error(e, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while reordering activity groups"
        ) from e


@router.put(
    "/{group_id}",
    response_model=ActivityGroupResponse,
    responses={
        400: {"description": "Invalid group data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Group not found"},
    }
)
async def update_activity_group(
    group_id: uuid.UUID,
    group_data: ActivityGroupUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Update an activity group."""
    service = ActivityGroupService(session)
    try:
        group = service.update_group(group_id, current_user.id, group_data)
        return group
    except ActivityGroupNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity group not found"
        ) from None
    except ValueError as e:
        log_error(e, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid group data"
        ) from None
    except Exception as e:
        log_error(e, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating activity group"
        ) from e


@router.delete(
    "/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Group not found"},
    }
)
async def delete_activity_group(
    group_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """
    Delete an activity group.

    Activities in this group will be ungrouped (group_id set to NULL).
    """
    service = ActivityGroupService(session)
    try:
        service.delete_group(group_id, current_user.id)
    except ActivityGroupNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity group not found"
        ) from None
    except Exception as e:
        log_error(e, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting activity group"
        ) from e
