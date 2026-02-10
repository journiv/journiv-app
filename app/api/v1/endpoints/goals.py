"""
Goal endpoints.
"""
import uuid
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError as PydanticValidationError
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.core.exceptions import ValidationError
from app.core.logging_config import log_error
from app.models.user import User
from app.schemas.goal import (
    GoalCreate,
    GoalReorderRequest,
    GoalResponse,
    GoalToggleRequest,
    GoalUpdate,
    GoalWithProgressResponse,
)
from app.schemas.goal_category import (
    GoalCategoryCreate,
    GoalCategoryReorderRequest,
    GoalCategoryResponse,
    GoalCategoryUpdate,
)
from app.services.goal_category_service import (
    GoalCategoryNotFoundError,
    GoalCategoryService,
)
from app.services.goal_service import GoalNotFoundError, GoalService

router = APIRouter(prefix="/goals", tags=["goals"])
category_router = APIRouter(prefix="/goal-categories", tags=["goals"])



@router.get(
    "",
    response_model=List[GoalWithProgressResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    },
)
async def get_goals(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    include_archived: bool = Query(False),
):
    goal_service = GoalService(session)
    rows = goal_service.list_goals_with_progress(
        current_user.id,
        include_archived=include_archived,
    )
    responses: list[GoalWithProgressResponse] = []
    for row in rows:
        goal_response = GoalWithProgressResponse.model_validate(row["goal"])
        goal_response.current_period_completed = row["current_period_completed"]
        goal_response.status = row.get("status")
        responses.append(goal_response)
    return responses


@router.put(
    "/reorder",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    },
)
async def reorder_goals(
    reorder_data: GoalReorderRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    goal_service = GoalService(session)
    updates = [(item.id, item.position) for item in reorder_data.updates]
    try:
        goal_service.reorder_goals(current_user.id, updates)
        return {"status": "ok"}
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while reordering goals",
        ) from exc


@router.post(
    "",
    response_model=GoalResponse,
    responses={
        400: {"description": "Invalid goal data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    },
)
async def create_goal(
    goal_data: GoalCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    goal_service = GoalService(session)
    try:
        return goal_service.create_goal(current_user.id, goal_data)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while creating goal",
        ) from exc


@router.put(
    "/{goal_id}",
    response_model=GoalResponse,
    responses={
        400: {"description": "Invalid goal data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Goal not found"},
    },
)
async def update_goal(
    goal_id: uuid.UUID,
    goal_data: GoalUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    goal_service = GoalService(session)
    try:
        return goal_service.update_goal(goal_id, current_user.id, goal_data)
    except GoalNotFoundError:
        raise HTTPException(status_code=404, detail="Goal not found") from None
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while updating goal",
        ) from exc


@router.delete(
    "/{goal_id}",
    response_model=GoalResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Goal not found"},
    },
)
async def archive_goal(
    goal_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    goal_service = GoalService(session)
    try:
        return goal_service.archive_goal(goal_id, current_user.id)
    except GoalNotFoundError:
        raise HTTPException(status_code=404, detail="Goal not found") from None
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while archiving goal",
        ) from exc


@router.post(
    "/{goal_id}/toggle",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Goal not found"},
    },
)
async def toggle_goal_completion(
    goal_id: uuid.UUID,
    toggle: GoalToggleRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    goal_service = GoalService(session)
    try:
        completed = goal_service.toggle_goal_completion(
            goal_id,
            current_user.id,
            toggle.logged_date,
            status=toggle.status,
        )
        return {"completed": completed}
    except GoalNotFoundError:
        raise HTTPException(status_code=404, detail="Goal not found") from None
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while toggling goal",
        ) from exc


@category_router.get(
    "",
    response_model=List[GoalCategoryResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    },
)
async def get_goal_categories(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    service = GoalCategoryService(session)
    return service.get_user_categories(current_user.id)


@category_router.post(
    "",
    response_model=GoalCategoryResponse,
    responses={
        400: {"description": "Invalid category data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    },
)
async def create_goal_category(
    category_data: GoalCategoryCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    service = GoalCategoryService(session)
    try:
        return service.create_category(current_user.id, category_data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while creating goal category",
        ) from exc


@category_router.put(
    "/reorder",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    },
)
async def reorder_goal_categories(
    reorder_data: GoalCategoryReorderRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    service = GoalCategoryService(session)
    updates = [(item.id, item.position) for item in reorder_data.updates]
    try:
        service.reorder_categories(current_user.id, updates)
        return {"status": "ok"}
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while reordering goal categories",
        ) from exc


@category_router.put(
    "/{category_id}",
    response_model=GoalCategoryResponse,
    responses={
        400: {"description": "Invalid category data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Category not found"},
    },
)
async def update_goal_category(
    category_id: uuid.UUID,
    category_data: GoalCategoryUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    service = GoalCategoryService(session)
    try:
        return service.update_category(category_id, current_user.id, category_data)
    except GoalCategoryNotFoundError:
        raise HTTPException(status_code=404, detail="Category not found") from None
    except (ValueError, PydanticValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while updating goal category",
        ) from exc


@category_router.delete(
    "/{category_id}",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Category not found"},
    },
)
async def delete_goal_category(
    category_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    service = GoalCategoryService(session)
    try:
        service.delete_category(category_id, current_user.id)
        return {"status": "ok"}
    except GoalCategoryNotFoundError:
        raise HTTPException(status_code=404, detail="Category not found") from None
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while deleting goal category",
        ) from exc
