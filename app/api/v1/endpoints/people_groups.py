"""
Person Group management endpoints.
"""
import uuid
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.core.logging_config import log_error
from app.models.person_group import PersonGroup
from app.models.user import User
from app.schemas.person import (
    PersonGroupCreate,
    PersonGroupReorderRequest,
    PersonGroupResponse,
    PersonGroupUpdate,
    PersonGroupWithPeopleResponse,
    PersonSummaryResponse,
)
from app.services.person_group_service import (
    PersonGroupNotFoundError,
    PersonGroupService,
)
from app.services.person_service import PersonService

router = APIRouter(prefix="/people-groups", tags=["people-groups"])


def _build_group_with_people_response(group: PersonGroup) -> PersonGroupWithPeopleResponse:
    people = sorted(
        [person for person in (group.people or []) if person.archived_at is None],
        key=lambda person: (person.name or "").lower(),
    )
    return PersonGroupWithPeopleResponse(
        id=group.id,
        user_id=group.user_id,
        name=group.name,
        color_value=group.color_value,
        icon=group.icon,
        position=group.position,
        created_at=group.created_at,
        updated_at=group.updated_at,
        people=[
            PersonSummaryResponse(
                id=person.id,
                name=person.name,
                nickname=person.nickname,
                profile_image_url=PersonService.build_profile_image_url(person),
            )
            for person in people
        ],
    )


@router.post(
    "/",
    response_model=PersonGroupResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Invalid group data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    },
)
async def create_person_group(
    group_data: PersonGroupCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Create a new person group."""
    service = PersonGroupService(session)
    try:
        return service.create_group(current_user.id, group_data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating person group",
        ) from exc


@router.get(
    "/",
    response_model=List[PersonGroupWithPeopleResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    },
)
async def get_person_groups(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Get all person groups for the current user, including grouped people."""
    service = PersonGroupService(session)
    try:
        groups = service.get_user_groups(current_user.id)
        return [_build_group_with_people_response(group) for group in groups]
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching person groups",
        ) from exc


@router.get(
    "/{group_id}",
    response_model=PersonGroupWithPeopleResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Group not found"},
    },
)
async def get_person_group(
    group_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Get a specific person group."""
    service = PersonGroupService(session)
    try:
        group = service.get_group_by_id(group_id, current_user.id)
        if not group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Person group not found",
            )
        return _build_group_with_people_response(group)
    except HTTPException:
        raise
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching person group",
        ) from exc


@router.put(
    "/reorder",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        400: {"description": "Bad request - invalid reorder data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Group not found"},
    },
)
async def reorder_person_groups(
    reorder_data: PersonGroupReorderRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Reorder person groups for the current user."""
    service = PersonGroupService(session)
    updates = [(item.id, item.position) for item in reorder_data.updates]
    try:
        service.reorder_groups(current_user.id, updates)
    except PersonGroupNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Person group not found or not owned by user",
        ) from None
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from None
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while reordering person groups",
        ) from exc


@router.put(
    "/{group_id}",
    response_model=PersonGroupResponse,
    responses={
        400: {"description": "Invalid group data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Group not found"},
    },
)
async def update_person_group(
    group_id: uuid.UUID,
    group_data: PersonGroupUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Update a person group."""
    service = PersonGroupService(session)
    try:
        return service.update_group(group_id, current_user.id, group_data)
    except PersonGroupNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Person group not found",
        ) from None
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from None
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating person group",
        ) from exc


@router.delete(
    "/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Group not found"},
    },
)
async def delete_person_group(
    group_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Delete a person group. People remain and are simply removed from this group."""
    service = PersonGroupService(session)
    try:
        service.delete_group(group_id, current_user.id)
    except PersonGroupNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Person group not found",
        ) from None
    except Exception as exc:
        log_error(exc, request_id=None, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting person group",
        ) from exc
