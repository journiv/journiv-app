"""
Journal endpoints.
"""
import uuid
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.core.exceptions import JournalNotFoundError, UserNotFoundError
from app.core.logging_config import log_error, log_user_action
from app.models.journal import Journal
from app.models.user import User
from app.schemas.journal import (
    JournalCreate,
    JournalMemberCreate,
    JournalMemberResponse,
    JournalMemberUpdate,
    JournalReorderRequest,
    JournalResponse,
    JournalUpdate,
)
from app.services.journal_access import JournalAccessDeniedError, JournalAccessService
from app.services.journal_service import JournalService

router = APIRouter(prefix="/journals", tags=["journals"])


def _journal_response(
    journal: Journal, access_level: str, owner: User
) -> JournalResponse:
    """Build a journal response with viewer-specific access and owner details.
    """
    response = JournalResponse.model_validate(journal)
    # These describe the viewer's relationship, not the journal record itself.
    response.access_level = access_level
    response.owner_id = owner.id
    response.owner_name = owner.name
    return response


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
    """Create a journal for the current user."""
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
    """List journals the current user owns or can access.

    By default excludes archived journals. Set include_archived=true to include them.
    """
    journal_service = JournalService(session)
    try:
        journals = journal_service.get_accessible_journals(current_user.id, include_archived)
        return [_journal_response(journal, level, owner) for journal, level, owner in journals]
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
    """List the current user's favorited journals."""
    journal_service = JournalService(session)
    try:
        journals = journal_service.get_favorite_journals(current_user.id)
        return journals
    except Exception as e:
        log_error(e, request_id=None, user_email=current_user.email)
        raise HTTPException(status_code=500, detail="An error occurred while fetching favorite journals") from None


@router.put(
    "/reorder",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Journal not found or not owned by user"},
        500: {"description": "Internal server error"},
    },
)
async def reorder_journals(
    reorder_data: JournalReorderRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
):
    """Reorder journals owned by the current user.

    Updates the position field for multiple journals in a single transaction.
    Journals are ordered by: is_favorite DESC, position ASC NULLS LAST, created_at DESC.
    """
    journal_service = JournalService(session)
    try:
        updates = [(item.id, item.position) for item in reorder_data.updates]
        journal_service.reorder_journals(current_user.id, updates)
        log_user_action(
            current_user.email,
            f"reordered {len(updates)} journals",
            request_id=None
        )
    except JournalNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        log_error(e, request_id=None, user_email=current_user.email)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while reordering journals"
        ) from None


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
    """Get a journal visible to the current user.

    The response includes the viewer's access level and the journal owner's details.
    """
    try:
        access = JournalAccessService(session).require(journal_id, current_user.id)
        owner = session.get(User, access.journal.user_id)
        return _journal_response(access.journal, access.level, owner)
    except JournalAccessDeniedError:
        raise HTTPException(status_code=404, detail="Journal not found") from None
    except HTTPException:
        raise
    except Exception as e:
        log_error(e, request_id=None, user_email=current_user.email)
        raise HTTPException(status_code=500, detail="An error occurred while fetching journal") from None


@router.get(
    "/{journal_id}/members",
    response_model=List[JournalMemberResponse],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Journal not found"},
    },
)
async def list_journal_members(
    journal_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> List[JournalMemberResponse]:
    """List a journal's collaborator roster for any user with read access.

    Roster membership remains owner-managed; this endpoint only exposes it.
    """
    try:
        JournalAccessService(session).require(journal_id, current_user.id)
        return [
            JournalMemberResponse(
                user_id=member.user_id,
                name=user.name,
                permission=member.permission,
                created_at=member.created_at,
                updated_at=member.updated_at,
            )
            for member, user in JournalService(session).list_members(journal_id)
        ]
    except JournalAccessDeniedError:
        raise HTTPException(status_code=404, detail="Journal not found") from None


@router.post(
    "/{journal_id}/members",
    response_model=JournalMemberResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Journal or user not found"},
        409: {"description": "User is already a journal member"},
    },
)
async def add_journal_member(
    journal_id: uuid.UUID,
    body: JournalMemberCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> JournalMemberResponse:
    """Add a collaborator to a journal.

    Only the journal owner can change roster membership.
    """
    try:
        JournalAccessService(session).require(journal_id, current_user.id, manage=True)
        member = JournalService(session).add_member(journal_id, body.user_id, body.permission)
        user = session.get(User, member.user_id)
        return JournalMemberResponse(
            user_id=user.id,
            name=user.name,
            permission=member.permission,
            created_at=member.created_at,
            updated_at=member.updated_at,
        )
    except JournalAccessDeniedError:
        raise HTTPException(status_code=404, detail="Journal not found") from None
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.put(
    "/{journal_id}/members/{user_id}",
    response_model=JournalMemberResponse,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Journal or journal member not found"},
    },
)
async def update_journal_member(
    journal_id: uuid.UUID,
    user_id: uuid.UUID,
    body: JournalMemberUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> JournalMemberResponse:
    """Change a collaborator's journal permission.

    Only the journal owner can change roster membership.
    """
    try:
        JournalAccessService(session).require(journal_id, current_user.id, manage=True)
        member = JournalService(session).update_member(journal_id, user_id, body.permission)
        user = session.get(User, user_id)
        return JournalMemberResponse(
            user_id=user.id,
            name=user.name,
            permission=member.permission,
            created_at=member.created_at,
            updated_at=member.updated_at,
        )
    except (JournalAccessDeniedError, JournalNotFoundError):
        raise HTTPException(status_code=404, detail="Journal not found") from None


@router.delete(
    "/{journal_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Journal or journal member not found"},
    },
)
async def remove_journal_member(
    journal_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> None:
    """Remove a collaborator from a journal.

    Only the journal owner can change roster membership.
    """
    try:
        JournalAccessService(session).require(journal_id, current_user.id, manage=True)
        JournalService(session).remove_member(journal_id, user_id)
    except (JournalAccessDeniedError, JournalNotFoundError):
        raise HTTPException(status_code=404, detail="Journal member not found") from None


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
    """Update a journal's editable properties.

    Only the journal owner may modify journal metadata.
    """
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
    """Delete a journal owned by the current user.

    Collaborators cannot delete journals they can access.
    """
    journal_service = JournalService(session)
    try:
        journal_service.delete_journal(journal_id, current_user.id)
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
    """Archive a journal owned by the current user.

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
