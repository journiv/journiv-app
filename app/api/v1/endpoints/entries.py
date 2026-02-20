"""
Entry endpoints.
"""
import logging
import uuid
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.core.exceptions import (
    EntryNotFoundError,
    JournalNotFoundError,
    ValidationError,
)
from app.core.logging_config import log_error, log_user_action
from app.core.media_signing import attach_signed_urls_to_delta
from app.models.moment import MomentMedia
from app.models.user import User
from app.schemas.entry import (
    EntryCreate,
    EntryDraftCreate,
    EntryResponse,
    EntryUpdate,
)
from app.services.entry_service import EntryService

router = APIRouter(prefix="/entries", tags=["entries"])
logger = logging.getLogger(__name__)


def _hydrate_entry_deltas(
    session: Session,
    entries: List,
    user_id: uuid.UUID,
) -> List[EntryResponse]:
    """Build entry responses with content_delta hydrated with signed media URLs."""
    responses = [EntryResponse.model_validate(entry) for entry in entries]

    # Collect all moment_ids that have content_delta needing hydration
    moment_ids = {
        r.moment_id for r in responses
        if r.content_delta is not None and r.moment_id is not None
    }
    if not moment_ids:
        return responses

    # Batch-load all media for the relevant moments
    media_items = list(session.exec(
        select(MomentMedia).where(MomentMedia.moment_id.in_(moment_ids))  # type: ignore[union-attr]
    ).all())

    # Group by moment_id
    media_by_moment: dict[uuid.UUID, list[MomentMedia]] = {}
    for media in media_items:
        media_by_moment.setdefault(media.moment_id, []).append(media)

    user_id_str = str(user_id)
    for response in responses:
        if response.content_delta is None or response.moment_id is None:
            continue
        moment_media = media_by_moment.get(response.moment_id, [])
        if not moment_media:
            continue
        delta_dict = (
            response.content_delta.model_dump()
            if hasattr(response.content_delta, "model_dump")
            else response.content_delta
        )
        hydrated = attach_signed_urls_to_delta(delta_dict, moment_media, user_id_str)
        if hydrated is not None:
            response.content_delta = response.content_delta.__class__(**hydrated)

    return responses


def _build_entry_responses(
    session: Session,
    entries: List,
    user_id: uuid.UUID,
) -> List[EntryResponse]:
    return _hydrate_entry_deltas(session, entries, user_id)


def _build_entry_response(
    session: Session,
    entry,
    user_id: uuid.UUID,
) -> EntryResponse:
    return _build_entry_responses(session, [entry], user_id)[0]

@router.post(
    "/",
    response_model=EntryResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Invalid entry data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Journal not found"},
        500: {"description": "Internal server error"},
    }
)
async def create_entry(
    entry_data: EntryCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Create a new journal entry."""
    entry_service = EntryService(session)
    try:
        entry = entry_service.create_entry(current_user.id, entry_data)
        log_user_action(current_user.email, f"created entry {entry.id}", request_id=None)
        return _build_entry_response(session, entry, current_user.id)
    except JournalNotFoundError:
        raise HTTPException(status_code=404, detail="Journal not found") from None
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        log_error(e, request_id=None, user_email=current_user.email)
        raise HTTPException(status_code=500, detail="An error occurred while creating entry") from None


@router.post(
    "/draft",
    response_model=EntryResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Invalid entry data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Journal not found"},
        500: {"description": "Internal server error"},
    }
)
async def create_draft_entry(
    entry_data: EntryDraftCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Create a new draft entry."""
    entry_service = EntryService(session)
    try:
        entry = entry_service.create_entry(current_user.id, entry_data, is_draft=True)
        log_user_action(current_user.email, f"created draft entry {entry.id}", request_id=None)
        return _build_entry_response(session, entry, current_user.id)
    except JournalNotFoundError:
        raise HTTPException(status_code=404, detail="Journal not found") from None
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        log_error(e, request_id=None, user_email=current_user.email)
        raise HTTPException(status_code=500, detail="An error occurred while creating draft entry") from None


@router.get(
    "/drafts",
    response_model=List[EntryResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        500: {"description": "Internal server error"},
    }
)
async def get_user_drafts(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    journal_id: Annotated[Optional[uuid.UUID], Query()] = None,
):
    """Get all draft entries for the current user."""
    try:
        entry_service = EntryService(session)
        entries = entry_service.get_user_drafts(
            user_id=current_user.id,
            limit=limit,
            offset=offset,
            journal_id=journal_id,
        )
        return _build_entry_responses(session, entries, current_user.id)
    except Exception as e:
        log_error(e, message="Unexpected error fetching draft entries", user_email=current_user.email)
        raise HTTPException(status_code=500, detail="An error occurred while fetching draft entries") from None


@router.get(
    "/",
    response_model=List[EntryResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        500: {"description": "Internal server error"},
    }
)
async def get_user_entries(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_drafts: Annotated[bool, Query()] = False,
):
    """
    Get all entries for the current user.

    Supports pagination via limit and offset parameters.
    Entries are sorted by created_at in descending order (newest first).
    Search/date filtering is handled by /moments.
    """
    try:
        entry_service = EntryService(session)
        entries = entry_service.get_user_entries(
            user_id=current_user.id,
            limit=limit,
            offset=offset,
            include_drafts=include_drafts,
        )
        return _build_entry_responses(session, entries, current_user.id)
    except Exception as e:
        log_error(e, message="Unexpected error fetching entries", user_email=current_user.email)
        raise HTTPException(status_code=500, detail="An error occurred while fetching entries") from None


@router.get(
    "/journal/{journal_id}",
    response_model=List[EntryResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Journal not found"},
        500: {"description": "Internal server error"},
    }
)
async def get_journal_entries(
    journal_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_drafts: Annotated[bool, Query()] = False,
    include_pinned: Annotated[bool, Query()] = True,
):
    """Get entries for a specific journal."""
    entry_service = EntryService(session)
    try:
        entries = entry_service.get_journal_entries(
            journal_id,
            current_user.id,
            limit,
            offset,
            include_drafts,
            include_pinned=include_pinned,
        )
        return _build_entry_responses(session, entries, current_user.id)
    except JournalNotFoundError:
        raise HTTPException(status_code=404, detail="Journal not found") from None
    except Exception as e:
        logger.error(
            "Unexpected error fetching journal entries",
            extra={"user_id": str(current_user.id), "journal_id": str(journal_id), "error": str(e)}
        )
        raise HTTPException(status_code=500, detail="An error occurred while fetching journal entries") from None


@router.get(
    "/{entry_id}",
    response_model=EntryResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Entry not found"},
        500: {"description": "Internal server error"},
    }
)
async def get_entry(
    entry_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Get a specific entry by ID."""
    try:
        entry_service = EntryService(session)
        entry = entry_service.get_entry_by_id(entry_id, current_user.id)
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")
        return _build_entry_response(session, entry, current_user.id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Unexpected error fetching entry",
            extra={"user_id": str(current_user.id), "entry_id": str(entry_id), "error": str(e)}
        )
        raise HTTPException(status_code=500, detail="An error occurred while fetching entry") from None


@router.put(
    "/{entry_id}",
    response_model=EntryResponse,
    responses={
        400: {"description": "Invalid entry data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Entry not found"},
        422: {"description": "Validation error (e.g., cannot move to archived journal)"},
        500: {"description": "Internal server error"},
    }
)
async def update_entry(
    entry_id: uuid.UUID,
    entry_data: EntryUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Update an entry's content, title, or other properties."""
    entry_service = EntryService(session)
    try:
        entry = entry_service.update_entry(entry_id, current_user.id, entry_data)
        log_user_action(current_user.email, "Updated entry", request_id=None)
        return _build_entry_response(session, entry, current_user.id)
    except EntryNotFoundError:
        raise HTTPException(status_code=404, detail="Entry not found") from None
    except JournalNotFoundError:
        raise HTTPException(status_code=404, detail="Target journal not found") from None
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        logger.error(
            "Unexpected error updating entry",
            extra={"user_id": str(current_user.id), "entry_id": str(entry_id), "error": str(e)}
        )
        raise HTTPException(status_code=500, detail="An error occurred while updating entry") from None


@router.delete(
    "/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Entry not found"},
        500: {"description": "Internal server error"},
    }
)
async def delete_entry(
    entry_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """
    Delete an entry.
    """
    entry_service = EntryService(session)
    try:
        entry_service.delete_entry(entry_id, current_user.id)
        log_user_action(current_user.email, "Deleted entry", request_id=None)
    except EntryNotFoundError:
        raise HTTPException(status_code=404, detail="Entry not found") from None
    except Exception as e:
        logger.error(
            "Unexpected error deleting entry",
            extra={"user_id": str(current_user.id), "entry_id": str(entry_id), "error": str(e)}
        )
        raise HTTPException(status_code=500, detail="An error occurred while deleting entry") from None

