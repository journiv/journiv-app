"""
Journal endpoints.
"""
import uuid
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.core.exceptions import JournalNotFoundError
from app.core.logging_config import log_error, log_user_action
from app.models.user import User
from app.schemas.journal import JournalCreate, JournalResponse, JournalUpdate
from app.services.journal_service import JournalService

router = APIRouter(prefix="/journals", tags=["journals"])


@router.post(
    "/",
    response_model=JournalResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Invalid journal data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        500: {"description": "Internal server error"},
    }
)
async def create_journal(
    journal_data: JournalCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """Create a new journal."""
    journal_service = JournalService(session)
    try:
        journal = journal_service.create_journal(current_user.id, journal_data)
        log_user_action(current_user.email, f"created journal {journal.id}", request_id=None)
        return journal
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        log_error(e, request_id=None, user_email=current_user.email)
        raise HTTPException(status_code=500, detail="An error occurred while creating journal") from None


@router.get(
    "/",
    response_model=List[JournalResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        500: {"description": "Internal server error"},
    }
)
async def get_user_journals(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    include_archived: bool = False,
):
    """
    Get all journals for the current user.

    By default excludes archived journals. Set include_archived=true to include them.
    """
    journal_service = JournalService(session)
    try:
        journals = journal_service.get_user_journals(current_user.id, include_archived)
        return journals
    except Exception as e:
        log_error(e, request_id=None, user_email=current_user.email)
        raise HTTPException(status_code=500, detail="An error occurred while fetching journals") from None


@router.get(
    "/favorites",
    response_model=List[JournalResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        500: {"description": "Internal server error"},
    }
)
async def get_favorite_journals(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """Get all journals marked as favorites."""
    journal_service = JournalService(session)
    try:
        journals = journal_service.get_favorite_journals(current_user.id)
        return journals
    except Exception as e:
        log_error(e, request_id=None, user_email=current_user.email)
        raise HTTPException(status_code=500, detail="An error occurred while fetching favorite journals") from None


@router.get(
    "/{journal_id}",
    response_model=JournalResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Journal not found"},
        500: {"description": "Internal server error"},
    }
)
async def get_journal(
    journal_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """Get a specific journal by ID."""
    journal_service = JournalService(session)
    try:
        journal = journal_service.get_journal_by_id(journal_id, current_user.id)
        if not journal:
            raise HTTPException(status_code=404, detail="Journal not found")
        return journal
    except HTTPException:
        raise
    except Exception as e:
        log_error(e, request_id=None, user_email=current_user.email)
        raise HTTPException(status_code=500, detail="An error occurred while fetching journal") from None


@router.put(
    "/{journal_id}",
    response_model=JournalResponse,
    responses={
        400: {"description": "Invalid journal data"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Journal not found"},
        500: {"description": "Internal server error"},
    }
)
async def update_journal(
    journal_id: uuid.UUID,
    journal_data: JournalUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """Update a journal's name, description, or other properties."""
    journal_service = JournalService(session)
    try:
        journal = journal_service.update_journal(journal_id, current_user.id, journal_data)
        log_user_action(current_user.email, f"updated journal {journal_id}", request_id=None)
        return journal
    except JournalNotFoundError:
        raise HTTPException(status_code=404, detail="Journal not found") from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        log_error(e, request_id=None, user_email=current_user.email)
        raise HTTPException(status_code=500, detail="An error occurred while updating journal") from None


@router.delete(
    "/{journal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Journal not found"},
        500: {"description": "Internal server error"},
    }
)
async def delete_journal(
    journal_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """
    Delete a journal.
    """
    journal_service = JournalService(session)
    try:
        await journal_service.delete_journal(journal_id, current_user.id)
        log_user_action(current_user.email, f"deleted journal {journal_id}", request_id=None)
    except JournalNotFoundError:
        raise HTTPException(status_code=404, detail="Journal not found") from None
    except Exception as e:
        log_error(e, request_id=None, user_email=current_user.email)
        raise HTTPException(status_code=500, detail="An error occurred while deleting journal") from None


@router.post(
    "/{journal_id}/favorite",
    response_model=JournalResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Journal not found"},
        500: {"description": "Internal server error"},
    }
)
async def toggle_favorite(
    journal_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """Toggle favorite status of a journal (on/off)."""
    journal_service = JournalService(session)
    try:
        journal = journal_service.toggle_favorite(journal_id, current_user.id)
        log_user_action(current_user.email, f"toggled favorite for journal {journal_id}", request_id=None)
        return journal
    except JournalNotFoundError:
        raise HTTPException(status_code=404, detail="Journal not found") from None
    except Exception as e:
        log_error(e, request_id=None, user_email=current_user.email)
        raise HTTPException(status_code=500, detail="An error occurred while toggling favorite status") from None


@router.post(
    "/{journal_id}/archive",
    response_model=JournalResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Journal not found"},
        500: {"description": "Internal server error"},
    }
)
async def archive_journal(
    journal_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """
    Archive a journal.

    Archived journals are hidden from default listings but remain accessible.
    """
    journal_service = JournalService(session)
    try:
        journal = journal_service.archive_journal(journal_id, current_user.id)
        log_user_action(current_user.email, f"archived journal {journal_id}", request_id=None)
        return journal
    except JournalNotFoundError:
        raise HTTPException(status_code=404, detail="Journal not found") from None
    except Exception as e:
        log_error(e, request_id=None, user_email=current_user.email)
        raise HTTPException(status_code=500, detail="An error occurred while archiving journal") from None


@router.post(
    "/{journal_id}/unarchive",
    response_model=JournalResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Journal not found"},
        500: {"description": "Internal server error"},
    }
)
async def unarchive_journal(
    journal_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)]
):
    """Unarchive a journal to restore it to active listings."""
    journal_service = JournalService(session)
    try:
        journal = journal_service.unarchive_journal(journal_id, current_user.id)
        log_user_action(current_user.email, f"unarchived journal {journal_id}", request_id=None)
        return journal
    except JournalNotFoundError:
        raise HTTPException(status_code=404, detail="Journal not found") from None
    except Exception as e:
        log_error(e, request_id=None, user_email=current_user.email)
        raise HTTPException(status_code=500, detail="An error occurred while unarchiving journal") from None


