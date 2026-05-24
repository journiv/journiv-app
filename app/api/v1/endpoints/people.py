"""
People endpoints.
"""
import uuid
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.core.logging_config import log_error
from app.models.user import User
from app.schemas.person import PersonCreate, PersonResponse, PersonSort, PersonUpdate
from app.services.person_service import PersonService

router = APIRouter(prefix="/people", tags=["people"])

PROFILE_IMAGE_READ_CHUNK_BYTES = 1024 * 1024


def _raise_internal_server_error(exc: Exception, user_id: uuid.UUID) -> None:
    log_error(exc, request_id=None, user_id=user_id)
    raise HTTPException(status_code=500, detail="Internal server error") from exc


def _map_person_value_error(exc: ValueError) -> HTTPException:
    message = str(exc)
    if message == "Person not found":
        return HTTPException(status_code=404, detail=message)
    return HTTPException(status_code=400, detail=message)


def _parse_sort_mode(sort: Optional[str]) -> PersonSort:
    if sort is None:
        return PersonSort.by_name
    normalized = sort.strip().lower()
    if normalized in {"by_name", "name"}:
        return PersonSort.by_name
    if normalized == "frequent":
        return PersonSort.frequent
    if normalized == "recent":
        return PersonSort.recent
    raise HTTPException(status_code=400, detail="Invalid sort value")


@router.post(
    "/",
    response_model=PersonResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Invalid person data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    },
)
async def create_person(
    person_data: PersonCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    service = PersonService(session)
    try:
        return service.create_person(current_user.id, person_data)
    except ValueError as exc:
        raise _map_person_value_error(exc) from None
    except Exception as exc:
        _raise_internal_server_error(exc, current_user.id)


@router.get(
    "/",
    response_model=List[PersonResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
    },
)
async def get_people(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    q: Optional[str] = Query(None, alias="q"),
    search: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    include_archived: bool = Query(False),
):
    search_term = search if search is not None else q
    sort_mode = _parse_sort_mode(sort)
    service = PersonService(session)
    try:
        return service.list_people(
            current_user.id,
            limit=limit,
            offset=offset,
            search=search_term,
            sort=sort_mode,
            include_archived=include_archived,
        )
    except Exception as exc:
        _raise_internal_server_error(exc, current_user.id)


@router.get(
    "/{person_id}",
    response_model=PersonResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Person not found"},
    },
)
async def get_person(
    person_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    service = PersonService(session)
    try:
        return service.get_person(current_user.id, person_id, include_archived=True)
    except ValueError as exc:
        raise _map_person_value_error(exc) from None
    except Exception as exc:
        _raise_internal_server_error(exc, current_user.id)


@router.put(
    "/{person_id}",
    response_model=PersonResponse,
    responses={
        400: {"description": "Invalid person data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Person not found"},
    },
)
async def update_person(
    person_id: uuid.UUID,
    person_data: PersonUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    service = PersonService(session)
    try:
        return service.update_person(current_user.id, person_id, person_data)
    except ValueError as exc:
        raise _map_person_value_error(exc) from None
    except Exception as exc:
        _raise_internal_server_error(exc, current_user.id)


@router.post(
    "/{person_id}/profile-image",
    response_model=PersonResponse,
    responses={
        400: {"description": "Invalid image data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Person not found"},
        413: {"description": "Image too large"},
    },
)
async def upload_person_profile_image(
    person_id: uuid.UUID,
    file: Annotated[UploadFile, File(description="Profile image file")],
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    service = PersonService(session)
    try:
        image_buffer = bytearray()
        while chunk := await file.read(PROFILE_IMAGE_READ_CHUNK_BYTES):
            image_buffer.extend(chunk)
            if len(image_buffer) > PersonService.PROFILE_IMAGE_MAX_BYTES:
                await file.close()
                raise HTTPException(
                    status_code=413,
                    detail="Profile image must be 10 MB or smaller",
                )
        image_bytes = bytes(image_buffer)
        return service.upload_profile_image(current_user.id, person_id, image_bytes)
    except HTTPException:
        raise
    except ValueError as exc:
        message = str(exc)
        if message == "Person not found":
            raise HTTPException(status_code=404, detail=message) from None
        if "10 MB or smaller" in message:
            raise HTTPException(status_code=413, detail=message) from None
        raise HTTPException(status_code=400, detail=message) from None
    except Exception as exc:
        _raise_internal_server_error(exc, current_user.id)


@router.delete(
    "/{person_id}/profile-image",
    response_model=PersonResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Person not found"},
    },
)
async def remove_person_profile_image(
    person_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    service = PersonService(session)
    try:
        return service.remove_profile_image(current_user.id, person_id)
    except ValueError as exc:
        raise _map_person_value_error(exc) from None
    except Exception as exc:
        _raise_internal_server_error(exc, current_user.id)


@router.delete(
    "/{person_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Person not found"},
    },
)
async def archive_person(
    person_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    service = PersonService(session)
    try:
        service.archive_person(current_user.id, person_id)
    except ValueError as exc:
        raise _map_person_value_error(exc) from None
    except Exception as exc:
        _raise_internal_server_error(exc, current_user.id)


@router.post(
    "/{person_id}/restore",
    response_model=PersonResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Person not found"},
    },
)
async def restore_person(
    person_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    service = PersonService(session)
    try:
        return service.restore_person(current_user.id, person_id)
    except ValueError as exc:
        raise _map_person_value_error(exc) from None
    except Exception as exc:
        _raise_internal_server_error(exc, current_user.id)


@router.post(
    "/{source_id}/merge/{target_id}",
    response_model=PersonResponse,
    responses={
        400: {"description": "Invalid merge request"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Person not found"},
    },
)
async def merge_people(
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    service = PersonService(session)
    try:
        return service.merge_people(current_user.id, source_id, target_id)
    except ValueError as exc:
        raise _map_person_value_error(exc) from None
    except Exception as exc:
        _raise_internal_server_error(exc, current_user.id)
