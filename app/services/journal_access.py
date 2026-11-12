"""Centralized authorization for owned and shared journals."""
import uuid
from dataclasses import dataclass

from sqlmodel import Session, select

from app.models.enums import JournalPermission
from app.models.journal import Journal
from app.models.journal_member import JournalMember


class JournalAccessDeniedError(Exception):
    """The caller has no permission for the requested journal capability."""


@dataclass(frozen=True)
class JournalAccess:
    journal: Journal
    level: str

    def can(self, permission: JournalPermission) -> bool:
        """Return whether this resolved access level grants a permission.
        """
        # READONLY is always true because an instance exists only after JournalAccessService.require confirmed ownership or membership.
        if permission == JournalPermission.READONLY:
            return True
        return self.level in {"owner", JournalPermission.EDIT.value}


class JournalAccessService:
    """Resolve a user's effective journal capability without leaking existence."""

    def __init__(self, session: Session) -> None:
        """Use this session to check journal access."""
        self.session = session

    def require(
        self,
        journal_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        edit: bool = False,
        manage: bool = False,
    ) -> JournalAccess:
        """Require the requested read, edit, or owner-management capability."""
        journal = self.session.get(Journal, journal_id)
        if not journal:
            raise JournalAccessDeniedError("Journal not found")
        if journal.user_id == user_id:
            # Owners skip the membership table entirely.
            access = JournalAccess(journal=journal, level="owner")
        else:
            membership = self.session.exec(
                select(JournalMember).where(
                    JournalMember.journal_id == journal_id,
                    JournalMember.user_id == user_id,
                )
            ).first()
            if not membership:
                # Keep inaccessible journals indistinguishable from missing ones.
                raise JournalAccessDeniedError("Journal not found")
            access = JournalAccess(journal=journal, level=membership.permission.value)
        if manage and access.level != "owner":
            raise JournalAccessDeniedError("Journal management is not permitted")
        if edit and not access.can(JournalPermission.EDIT):
            raise JournalAccessDeniedError("Journal editing is not permitted")
        return access
