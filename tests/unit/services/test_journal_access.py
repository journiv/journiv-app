"""Shared journal access policy coverage."""

import uuid
from datetime import date
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, create_engine, select

from app.api.v1.endpoints.journals import (
    add_journal_member,
    list_journal_members,
    remove_journal_member,
    update_journal_member,
)
from app.core.exceptions import (
    EntryNotFoundError,
    JournalNotFoundError,
    MediaNotFoundError,
    UserNotFoundError,
)
from app.models.base import BaseModel
from app.models.entry import Entry
from app.models.enums import ExportType, JournalPermission, MediaType, UploadStatus
from app.models.journal import Journal
from app.models.journal_member import JournalMember
from app.models.integration import Integration, IntegrationProvider
from app.models.moment import Moment, MomentMedia
from app.models.moment_person_link import MomentPersonLink
from app.models.person import Person
from app.models.user import User
from app.schemas.entry import EntryCreate, EntryDraftCreate, EntryResponse, EntryUpdate
from app.schemas.journal import JournalMemberCreate, JournalMemberUpdate
from app.schemas.media import MediaBatchSignItem, MediaBatchSignRequest
from app.schemas.moment import MemoriesAppliedFilter, MomentUpdate
from app.services.analytics_service import AnalyticsService
from app.services.entry_service import EntryService
from app.services.export_service import ExportService
from app.services.journal_access import (
    JournalAccessDeniedError,
    JournalAccessService,
)
from app.services.journal_service import JournalService
from app.services.import_job_service import ImportJobService
from app.services.immich_face_service import ImmichFaceService
from app.services.media_service import MediaService
from app.services.moment_lookup import MomentNotFoundError, get_accessible_moment
from app.services.moment_service import MomentService
from app.services.person_service import PersonService
from app.services.pdf_service import EntryPDFService, PDFEntryNotFoundError
from app.services.tag_service import TagService
from app.services.user_service import UserService


def _user(email: str) -> User:
    """Build a test user from an email address."""
    return User(email=email, password="password", name=email.split("@")[0])


def _create_shared_draft_media(
    permission: JournalPermission = JournalPermission.READONLY,
):
    """Create an owner's draft image and a journal member."""
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    owner = _user(f"owner-{uuid.uuid4().hex}@example.com")
    reader = _user(f"reader-{uuid.uuid4().hex}@example.com")
    session.add_all([owner, reader])
    session.commit()
    journal = Journal(user_id=owner.id, title="Shared")
    moment = Moment(user_id=owner.id, logged_date_tz=date(2026, 9, 30))
    session.add_all([journal, moment])
    session.commit()
    media = MomentMedia(
        moment_id=moment.id,
        media_type=MediaType.IMAGE,
        file_path="images/draft.jpg",
        file_size=1,
        mime_type="image/jpeg",
        upload_status=UploadStatus.COMPLETED,
    )
    session.add_all([
        Entry(
            user_id=owner.id,
            journal_id=journal.id,
            moment_id=moment.id,
            is_draft=True,
        ),
        media,
        JournalMember(
            journal_id=journal.id,
            user_id=reader.id,
            permission=permission,
        ),
    ])
    session.commit()
    return session, owner, reader, journal, media


@pytest.mark.asyncio
@pytest.mark.parametrize("duplicate", [True, False])
async def test_add_member_rolls_back_integrity_errors(monkeypatch, duplicate):
    """Roll back failed inserts and report only duplicate memberships as conflicts."""
    session, owner, member, journal, _ = _create_shared_draft_media()
    message = (
        "UNIQUE constraint failed: journal_member.journal_id, journal_member.user_id"
        if duplicate else "FOREIGN KEY constraint failed"
    )
    error = IntegrityError("insert", {}, Exception(message))
    monkeypatch.setattr(JournalService, "add_member", MagicMock(side_effect=error))
    rollback = MagicMock(wraps=session.rollback)
    monkeypatch.setattr(session, "rollback", rollback)
    body = JournalMemberCreate(user_id=member.id, permission=JournalPermission.READONLY)

    if duplicate:
        with pytest.raises(HTTPException) as caught:
            await add_journal_member(journal.id, body, owner, session)
        assert caught.value.status_code == 409
    else:
        with pytest.raises(IntegrityError) as caught:
            await add_journal_member(journal.id, body, owner, session)
        assert caught.value is error
    rollback.assert_called_once()


def test_deleted_collaborator_draft_never_becomes_owner_draft():
    """An unknown draft author does not grant the journal owner access."""
    session, owner, member, journal, media = _create_shared_draft_media(JournalPermission.EDIT)
    entry = session.exec(select(Entry).where(Entry.moment_id == media.moment_id)).one()
    entry.created_by_user_id = None
    session.add(entry)
    session.commit()
    service = EntryService(session)
    assert service.get_entry_by_id(entry.id, owner.id) is None
    assert entry.id not in {item.id for item in service.get_journal_entries(journal.id, owner.id, include_drafts=True)}
    with pytest.raises(EntryNotFoundError):
        service.update_entry(entry.id, owner.id, EntryUpdate(is_draft=False))


def test_deleting_collaborator_removes_draft_and_anonymizes_published_entry():
    """Deleting an author removes drafts while preserving published entries."""
    session, owner, member, journal, media = _create_shared_draft_media(JournalPermission.EDIT)
    session.execute(text("PRAGMA foreign_keys=ON"))
    draft = session.exec(select(Entry).where(Entry.moment_id == media.moment_id)).one()
    draft.created_by_user_id = member.id
    draft_id = draft.id
    moment = Moment(user_id=owner.id, logged_date_tz=date(2026, 9, 29))
    session.add(moment)
    session.flush()
    published = Entry(user_id=owner.id, journal_id=journal.id, moment_id=moment.id,
                      created_by_user_id=member.id, is_draft=False)
    session.add_all([draft, published])
    session.commit()
    published_id = published.id

    UserService(session).delete_user(str(member.id), bypass_admin_check=True)
    session.expire_all()
    assert session.get(Entry, draft_id) is None
    remaining = session.get(Entry, published_id)
    assert remaining is not None
    assert remaining.created_by_user_id is None
    assert EntryResponse.model_validate(remaining).author_name == "deleted user"


@pytest.mark.asyncio
@pytest.mark.parametrize("permission,is_author,allowed", [
    (JournalPermission.EDIT, True, True),
    (JournalPermission.EDIT, False, False),
    (JournalPermission.READONLY, True, False),
])
async def test_immich_suggestions_require_draft_author_with_edit_access(permission, is_author, allowed):
    """Only draft authors with edit access can request Immich suggestions."""
    session, _, member, _, media = _create_shared_draft_media(permission)
    entry = session.exec(select(Entry).where(Entry.moment_id == media.moment_id)).one()
    if is_author:
        entry.created_by_user_id = member.id
    media.external_provider = "immich"
    media.external_asset_id = "asset-1"
    session.add_all([entry, media])
    session.commit()
    service = ImmichFaceService(session)
    service.get_batch_faces = AsyncMock(return_value=MagicMock(results={}))

    if allowed:
        result = await service.get_moment_suggestions(member.id, media.moment_id)
        assert result.people == []
        service.get_batch_faces.assert_awaited_once_with(member.id, ["asset-1"], refresh=False)
    else:
        with pytest.raises(ValueError, match="Moment not found"):
            await service.get_moment_suggestions(member.id, media.moment_id)
        service.get_batch_faces.assert_not_awaited()


@pytest.mark.parametrize("dispatch_fails", [False, True])
def test_shared_draft_deletion_cleans_media_as_moment_owner(monkeypatch, dispatch_fails):
    """Queued and fallback media cleanup use the moment owner's identity."""
    session, owner, editor, _, media = _create_shared_draft_media(JournalPermission.EDIT)
    entry = session.exec(select(Entry).where(Entry.moment_id == media.moment_id)).one()
    entry.created_by_user_id = editor.id
    session.add(entry)
    session.commit()
    should_remove = MagicMock(return_value=True)
    cleanup = MagicMock()
    dispatch = MagicMock(side_effect=RuntimeError("unavailable") if dispatch_fails else None)
    monkeypatch.setattr(MediaService, "_should_remove_immich_asset", should_remove)
    monkeypatch.setattr(MediaService, "delete_media_files_post_commit", cleanup)
    monkeypatch.setattr("app.core.celery_app.celery_app.send_task", dispatch)

    result = MomentService(session).delete_moment(media.moment_id, editor.id)

    assert should_remove.call_args.args[2] == owner.id
    assert dispatch.call_args.kwargs["args"][0] == str(owner.id)
    assert result["cleanup_queued"] is not dispatch_fails
    if dispatch_fails:
        # If queuing fails, cleanup runs synchronously using the owner's ID.
        assert cleanup.call_args.args[0] == owner.id
    else:
        cleanup.assert_not_called()


@pytest.mark.parametrize("permission", [JournalPermission.EDIT, JournalPermission.READONLY])
def test_shared_moment_tags_respect_read_and_edit_permissions(permission):
    """Members can read published tags, but only editors can add them."""
    session, _, member, _, media = _create_shared_draft_media(permission)
    entry = session.exec(select(Entry).where(Entry.moment_id == media.moment_id)).one()
    service = TagService(session)
    with pytest.raises(ValueError, match="Moment not found"):
        service.get_moment_tags(media.moment_id, member.id)
    entry.is_draft = False
    session.add(entry)
    session.commit()
    assert service.get_moment_tags(media.moment_id, member.id) == []
    tag = service.create_or_get_tags(member.id, ["shared"])[0]
    if permission == JournalPermission.EDIT:
        service.add_tag_to_moment(media.moment_id, tag.id, member.id)
        assert len(service.bulk_add_tags_to_moment(media.moment_id, ["another"], member.id)) == 2
    else:
        with pytest.raises(ValueError, match="Moment not found"):
            service.add_tag_to_moment(media.moment_id, tag.id, member.id)
        with pytest.raises(ValueError, match="Moment not found"):
            service.bulk_add_tags_to_moment(media.moment_id, ["another"], member.id)


def test_entry_pdf_respects_shared_access_and_draft_authorship(monkeypatch):
    """PDF exports require journal access and respect draft authorship."""
    session, owner, member, journal, media = _create_shared_draft_media()
    entry = session.exec(select(Entry).where(Entry.moment_id == media.moment_id)).one()
    service = EntryPDFService(session)
    monkeypatch.setattr(service, "_render_entry_pdf", MagicMock(return_value=BytesIO(b"pdf")))

    with pytest.raises(PDFEntryNotFoundError):
        service.generate_owned_entry_pdf(entry_id=entry.id, user_id=member.id)
    entry.is_draft = False
    session.add(entry)
    session.commit()
    assert service.generate_owned_entry_pdf(entry_id=entry.id, user_id=member.id)[0].getvalue() == b"pdf"
    entry.is_draft = True
    entry.created_by_user_id = member.id
    session.add(entry)
    session.commit()
    assert service.generate_owned_entry_pdf(entry_id=entry.id, user_id=member.id)[0].getvalue() == b"pdf"
    with pytest.raises(PDFEntryNotFoundError):
        service.generate_owned_entry_pdf(entry_id=entry.id, user_id=owner.id)
    membership = session.exec(select(JournalMember).where(JournalMember.journal_id == journal.id)).one()
    session.delete(membership)
    session.commit()
    with pytest.raises(PDFEntryNotFoundError):
        service.generate_owned_entry_pdf(entry_id=entry.id, user_id=member.id)


def test_auto_memories_include_shared_published_moments(monkeypatch):
    """Auto memories include shared published moments but exclude drafts."""
    session, owner, member, journal, media = _create_shared_draft_media()
    moment = session.get(Moment, media.moment_id)
    moment.logged_date_tz = date(2025, 2, 23)
    entry = session.exec(select(Entry).where(Entry.moment_id == moment.id)).one()
    entry.is_draft = False
    hidden = Moment(user_id=owner.id, logged_date_tz=date(2025, 2, 23))
    session.add_all([moment, entry, hidden])
    session.commit()
    session.add(Entry(user_id=owner.id, journal_id=journal.id, moment_id=hidden.id, is_draft=True))
    session.commit()
    service = MomentService(session)
    monkeypatch.setattr(service, "_resolve_user_local_today", lambda user_id: date(2026, 2, 23))

    memories, applied = service.get_memories(member.id)
    assert applied == MemoriesAppliedFilter.last_years
    assert [item.id for item in memories] == [moment.id]


@pytest.mark.parametrize("permission,is_draft,allowed", [
    (JournalPermission.EDIT, False, True),
    (JournalPermission.READONLY, False, False),
    (JournalPermission.EDIT, True, False),
])
def test_import_job_lock_requires_editable_moment(permission, is_draft, allowed):
    """Import job creation requires edit access to the visible moment."""
    session, _, member, _, media = _create_shared_draft_media(permission)
    entry = session.exec(select(Entry).where(Entry.moment_id == media.moment_id)).one()
    entry.is_draft = is_draft
    session.add(entry)
    session.commit()
    if allowed:
        ImportJobService._lock_moment_for_job_creation(session, media.moment_id, member.id)
    else:
        with pytest.raises(ValueError, match="Moment not found"):
            ImportJobService._lock_moment_for_job_creation(session, media.moment_id, member.id)


@pytest.mark.asyncio
async def test_batch_sign_shared_immich_respects_visibility_and_owner_integration():
    """Sign shared Immich media URLs only when visible and its owner's integration is active."""
    session, owner, reader, journal, media = _create_shared_draft_media()
    media.external_provider = "immich"
    media.external_asset_id = str(uuid.uuid4())
    media.file_path = None
    session.add(media)
    session.add(Integration(
        user_id=owner.id, provider=IntegrationProvider.IMMICH,
        base_url="http://immich.test", access_token_encrypted="encrypted",
        external_user_id="immich-user", is_active=True,
    ))
    session.commit()
    request = MediaBatchSignRequest(items=[MediaBatchSignItem(id=str(media.id), variant="original")])
    service = MediaService()

    assert (await service.batch_sign_media(request, reader.id, session)).errors[0].error == "Media not found"
    entry = session.exec(select(Entry).where(Entry.moment_id == media.moment_id)).one()
    entry.is_draft = False
    session.add(entry)
    session.commit()
    assert len((await service.batch_sign_media(request, reader.id, session)).results) == 1

    integration = session.exec(select(Integration).where(Integration.user_id == owner.id)).one()
    integration.is_active = False
    session.add(integration)
    session.commit()
    assert (await service.batch_sign_media(request, reader.id, session)).errors[0].error == "Immich integration not active"

    member = session.exec(select(JournalMember).where(JournalMember.journal_id == journal.id)).one()
    session.delete(member)
    session.commit()
    assert (await service.batch_sign_media(request, reader.id, session)).errors[0].error == "Media not found"


def _create_shared_published_and_draft_moments(
    permission: JournalPermission,
):
    """Create published and draft Moments in a shared journal."""
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    owner = _user(f"owner-{uuid.uuid4().hex}@example.com")
    member = _user(f"member-{uuid.uuid4().hex}@example.com")
    session.add_all([owner, member])
    session.commit()
    journal = Journal(user_id=owner.id, title="Shared")
    published = Moment(user_id=owner.id, logged_date_tz=date(2026, 9, 30))
    draft = Moment(user_id=owner.id, logged_date_tz=date(2026, 9, 29))
    session.add_all([journal, published, draft])
    session.commit()
    session.add_all([
        Entry(
            user_id=owner.id,
            journal_id=journal.id,
            moment_id=published.id,
            is_draft=False,
        ),
        Entry(
            user_id=owner.id,
            journal_id=journal.id,
            moment_id=draft.id,
            is_draft=True,
        ),
        JournalMember(
            journal_id=journal.id,
            user_id=member.id,
            permission=permission,
        ),
    ])
    session.commit()
    return session, member, published, draft


def _create_shared_journal_for_actor(actor: str):
    """Create only the user and membership needed by one matrix row."""
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    owner = _user(f"owner-{uuid.uuid4().hex}@example.com")
    session.add(owner)
    session.commit()
    journal = Journal(user_id=owner.id, title="Shared")
    session.add(journal)
    session.commit()
    if actor == "owner":
        return session, owner, owner, journal

    actor_user = _user(f"{actor}-{uuid.uuid4().hex}@example.com")
    session.add(actor_user)
    session.commit()
    permission = {
        "reader": JournalPermission.READONLY,
        "editor": JournalPermission.EDIT,
    }.get(actor)
    if permission:
        session.add(JournalMember(journal_id=journal.id, user_id=actor_user.id, permission=permission))
        session.commit()
    return session, owner, actor_user, journal


@pytest.mark.parametrize(
    ("actor", "edit", "manage", "allowed"),
    [
        ("owner", False, False, True),
        ("owner", True, False, True),
        ("owner", False, True, True),
        ("reader", False, False, True),
        ("reader", True, False, False),
        ("reader", False, True, False),
        ("editor", False, False, True),
        ("editor", True, False, True),
        ("editor", False, True, False),
        ("outsider", False, False, False),
        ("outsider", True, False, False),
        ("missing", False, False, False),
    ],
)
def test_member_permissions_distinguish_read_and_edit_access(actor, edit, manage, allowed):
    """Check read, edit, and management access for each role."""
    setup_actor = "outsider" if actor == "missing" else actor
    session, _, current_user, journal = _create_shared_journal_for_actor(setup_actor)
    journal_id = uuid.uuid4() if actor == "missing" else journal.id

    expected_levels = {"owner": "owner", "reader": "readonly", "editor": "edit"}
    if allowed:
        access = JournalAccessService(session).require(
            journal_id, current_user.id, edit=edit, manage=manage
        )
        assert access.level == expected_levels[actor]
    else:
        with pytest.raises(JournalAccessDeniedError, match="Journal not found|not permitted"):
            JournalAccessService(session).require(
                journal_id, current_user.id, edit=edit, manage=manage
            )


def test_permission_downgrade_and_removal_revoke_access():
    """Check that permission changes take effect immediately."""
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    owner = _user(f"owner-{uuid.uuid4().hex}@example.com")
    member = _user(f"member-{uuid.uuid4().hex}@example.com")
    session.add_all([owner, member])
    session.commit()
    journal = Journal(user_id=owner.id, title="Shared")
    session.add(journal)
    session.commit()
    service = JournalService(session)
    service.add_member(journal.id, member.id, JournalPermission.EDIT)

    assert JournalAccessService(session).require(journal.id, member.id, edit=True).level == "edit"

    service.update_member(journal.id, member.id, JournalPermission.READONLY)

    assert JournalAccessService(session).require(journal.id, member.id).level == "readonly"
    with pytest.raises(JournalAccessDeniedError, match="Journal editing is not permitted"):
        JournalAccessService(session).require(journal.id, member.id, edit=True)

    service.remove_member(journal.id, member.id)

    with pytest.raises(JournalAccessDeniedError, match="Journal not found"):
        JournalAccessService(session).require(journal.id, member.id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("actor", "operation", "allowed"),
    [
        ("owner", "add", True),
        ("owner", "update", True),
        ("owner", "remove", True),
        ("editor", "add", False),
        ("editor", "update", False),
        ("editor", "remove", False),
        ("reader", "add", False),
        ("reader", "update", False),
        ("reader", "remove", False),
        ("outsider", "add", False),
        ("outsider", "update", False),
        ("outsider", "remove", False),
    ],
)
async def test_only_owner_can_mutate_shared_journal_roster(actor, operation, allowed):
    """Only the owner can add, update, or remove members."""
    session, _, current_user, journal = _create_shared_journal_for_actor(actor)
    target = _user(f"target-{uuid.uuid4().hex}@example.com")
    session.add(target)
    if operation != "add":
        session.add(
            JournalMember(
                journal_id=journal.id,
                user_id=target.id,
                permission=JournalPermission.READONLY,
            )
        )
    session.commit()
    if allowed:
        if operation == "add":
            response = await add_journal_member(
                journal.id,
                JournalMemberCreate(user_id=target.id, permission=JournalPermission.READONLY),
                current_user,
                session,
            )
            assert response.user_id == target.id
            assert response.permission == JournalPermission.READONLY
        elif operation == "update":
            response = await update_journal_member(
                journal.id,
                target.id,
                JournalMemberUpdate(permission=JournalPermission.EDIT),
                current_user,
                session,
            )
            assert response.permission == JournalPermission.EDIT
        else:
            assert await remove_journal_member(journal.id, target.id, current_user, session) is None
    else:
        with pytest.raises(HTTPException) as exc_info:
            if operation == "add":
                await add_journal_member(
                    journal.id,
                    JournalMemberCreate(user_id=target.id, permission=JournalPermission.READONLY),
                    current_user,
                    session,
                )
            elif operation == "update":
                await update_journal_member(
                    journal.id,
                    target.id,
                    JournalMemberUpdate(permission=JournalPermission.EDIT),
                    current_user,
                    session,
                )
            else:
                await remove_journal_member(journal.id, target.id, current_user, session)
        assert exc_info.value.status_code == 404

    member = session.exec(
        select(JournalMember).where(
            JournalMember.journal_id == journal.id,
            JournalMember.user_id == target.id,
        )
    ).first()
    if (operation == "remove" and allowed) or (operation == "add" and not allowed):
        assert member is None
    else:
        assert member is not None
        assert member.permission == (
            JournalPermission.EDIT if operation == "update" and allowed else JournalPermission.READONLY
        )


def test_adding_a_missing_user_raises_user_not_found_error():
    """Reject adding a journal member who does not exist."""
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    owner = _user(f"owner-{uuid.uuid4().hex}@example.com")
    session.add(owner)
    session.commit()
    journal = Journal(user_id=owner.id, title="Shared")
    session.add(journal)
    session.commit()

    with pytest.raises(UserNotFoundError, match="User not found"):
        JournalService(session).add_member(
            journal.id,
            uuid.uuid4(),
            JournalPermission.READONLY,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("permission", [JournalPermission.READONLY, JournalPermission.EDIT])
async def test_member_can_list_shared_journal_roster(permission):
    """Members can view the roster without exposing emails."""
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    owner = _user(f"owner-{uuid.uuid4().hex}@example.com")
    member = _user(f"member-{uuid.uuid4().hex}@example.com")
    session.add_all([owner, member])
    session.commit()
    journal = Journal(user_id=owner.id, title="Shared")
    session.add(journal)
    session.commit()
    session.add(
        JournalMember(
            journal_id=journal.id,
            user_id=member.id,
            permission=permission,
        )
    )
    session.commit()

    roster = await list_journal_members(journal.id, member, session)

    assert [(item.user_id, item.permission) for item in roster] == [
        (member.id, permission)
    ]
    assert "email" not in roster[0].model_dump()


def test_edit_member_can_access_a_shared_journal_moment_for_media_changes():
    """Catches a regression to direct Moment ownership in MediaService."""
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    owner = _user(f"owner-{uuid.uuid4().hex}@example.com")
    editor = _user(f"editor-{uuid.uuid4().hex}@example.com")
    session.add_all([owner, editor])
    session.commit()
    journal = Journal(user_id=owner.id, title="Shared")
    moment = Moment(user_id=owner.id, logged_date_tz=date(2026, 9, 30))
    session.add_all([journal, moment])
    session.commit()
    session.add_all([
        Entry(user_id=owner.id, journal_id=journal.id, moment_id=moment.id),
        JournalMember(
            journal_id=journal.id,
            user_id=editor.id,
            permission=JournalPermission.EDIT,
        ),
    ])
    session.commit()

    assert MediaService(session)._get_moment_for_user(session, moment.id, editor.id) == moment


def test_edit_member_cannot_update_shared_moment_metadata():
    """Catches Moment metadata updates treating edit access as ownership."""
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    owner = _user(f"owner-{uuid.uuid4().hex}@example.com")
    editor = _user(f"editor-{uuid.uuid4().hex}@example.com")
    session.add_all([owner, editor])
    session.commit()
    journal = Journal(user_id=owner.id, title="Shared")
    moment = Moment(user_id=owner.id, logged_date_tz=date(2026, 9, 30), note="Owner note")
    session.add_all([journal, moment])
    session.commit()
    session.add_all([
        Entry(user_id=owner.id, journal_id=journal.id, moment_id=moment.id),
        JournalMember(
            journal_id=journal.id,
            user_id=editor.id,
            permission=JournalPermission.EDIT,
        ),
    ])
    session.commit()

    with pytest.raises(MomentNotFoundError, match="Moment not found"):
        MomentService(session).update_moment(
            moment.id, editor.id, MomentUpdate(note="Editor overwrite")
        )

    assert session.get(Moment, moment.id).note == "Owner note"


@pytest.mark.parametrize(
    "permission", [JournalPermission.READONLY, JournalPermission.EDIT]
)
def test_member_timeline_hides_shared_drafts_even_when_requested(permission):
    """Members cannot opt into another person's draft through the timeline."""
    session, member, published, draft = _create_shared_published_and_draft_moments(
        permission
    )

    moments, _, _ = MomentService(session).get_moments(
        member.id, include_drafts=True
    )

    assert published.id in [moment.id for moment in moments]
    assert draft.id not in [moment.id for moment in moments]


@pytest.mark.parametrize(
    "permission", [JournalPermission.READONLY, JournalPermission.EDIT]
)
def test_member_entry_listing_hides_shared_drafts_even_when_requested(permission):
    """Members cannot opt into another person's draft through the entry listing."""
    session, member, published, draft = _create_shared_published_and_draft_moments(
        permission
    )

    entries = EntryService(session).get_user_entries(member.id, include_drafts=True)

    assert published.id in [entry.moment_id for entry in entries]
    assert draft.id not in [entry.moment_id for entry in entries]


@pytest.mark.parametrize(
    "permission", [JournalPermission.READONLY, JournalPermission.EDIT]
)
def test_member_calendar_hides_shared_drafts(permission):
    """Calendar summaries use the same draft privacy rule as the timeline."""
    session, member, published, draft = _create_shared_published_and_draft_moments(
        permission
    )

    moments = MomentService(session).get_calendar_summary(member.id)

    assert published.id in [moment.id for moment in moments]
    assert draft.id not in [moment.id for moment in moments]


def test_entry_listing_includes_entries_from_journals_shared_with_the_viewer():
    """Catches a regression to filtering the global feed by Entry.user_id only."""
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    owner = _user(f"owner-{uuid.uuid4().hex}@example.com")
    reader = _user(f"reader-{uuid.uuid4().hex}@example.com")
    session.add_all([owner, reader])
    session.commit()
    journal = Journal(user_id=owner.id, title="Shared")
    moment = Moment(user_id=owner.id, logged_date_tz=date(2026, 9, 30))
    session.add_all([journal, moment])
    session.commit()
    entry = Entry(user_id=owner.id, journal_id=journal.id, moment_id=moment.id)
    session.add_all([
        entry,
        JournalMember(
            journal_id=journal.id,
            user_id=reader.id,
            permission=JournalPermission.READONLY,
        ),
    ])
    session.commit()

    assert EntryService(session).get_user_entries(reader.id) == [entry]


def test_media_library_includes_completed_media_from_shared_journal_moments():
    """Catches a regression to filtering the media library by Moment.user_id."""
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    owner = _user(f"owner-{uuid.uuid4().hex}@example.com")
    reader = _user(f"reader-{uuid.uuid4().hex}@example.com")
    session.add_all([owner, reader])
    session.commit()
    journal = Journal(user_id=owner.id, title="Shared")
    moment = Moment(user_id=owner.id, logged_date_tz=date(2026, 9, 30))
    session.add_all([journal, moment])
    session.commit()
    media = MomentMedia(
        moment_id=moment.id,
        media_type=MediaType.IMAGE,
        file_path="images/shared.jpg",
        file_size=1,
        mime_type="image/jpeg",
        upload_status=UploadStatus.COMPLETED,
    )
    session.add_all([
        Entry(user_id=owner.id, journal_id=journal.id, moment_id=moment.id),
        media,
        JournalMember(
            journal_id=journal.id,
            user_id=reader.id,
            permission=JournalPermission.READONLY,
        ),
    ])
    session.commit()

    items, _, _ = MediaService(session).get_media_library(session, reader.id)

    assert [item.id for item in items] == [media.id]


def test_moment_media_thumbnails_include_signed_url_for_completed_owner_image():
    """Catches timeline responses dropping a completed image thumbnail URL."""
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    owner = _user(f"owner-{uuid.uuid4().hex}@example.com")
    session.add(owner)
    session.commit()
    moment = Moment(user_id=owner.id, logged_date_tz=date(2026, 9, 30))
    session.add(moment)
    session.commit()
    media = MomentMedia(
        moment_id=moment.id,
        media_type=MediaType.IMAGE,
        file_path="images/owner.jpg",
        file_size=1,
        thumbnail_path="images/thumbnails/thumb_owner.jpg",
        mime_type="image/jpeg",
        upload_status=UploadStatus.COMPLETED,
    )
    session.add(media)
    session.commit()

    media_counts, media_map = MediaService(session).get_moment_media_thumbnails(
        session, owner.id, [moment.id]
    )

    assert media_counts == {moment.id: 1}
    assert media_map[moment.id][0].signed_thumbnail_url is not None


def test_moment_media_thumbnails_filter_inaccessible_moments():
    """Return thumbnails only for visible moments in a mixed batch."""
    session, owner, reader, _, draft_media = _create_shared_draft_media()
    published = Moment(user_id=owner.id, logged_date_tz=date(2026, 9, 29))
    session.add(published)
    session.commit()
    draft = session.exec(select(Entry).where(Entry.moment_id == draft_media.moment_id)).one()
    session.add(Entry(user_id=owner.id, journal_id=draft.journal_id, moment_id=published.id))
    session.add(MomentMedia(
        moment_id=published.id, media_type=MediaType.IMAGE,
        file_path="images/published.jpg", file_size=1, mime_type="image/jpeg",
        upload_status=UploadStatus.COMPLETED,
    ))
    session.commit()
    service = MediaService(session)

    assert service.get_moment_media_thumbnails(session, reader.id, [draft_media.moment_id]) == ({}, {})
    counts, thumbnails = service.get_moment_media_thumbnails(
        session, reader.id, [draft_media.moment_id, published.id, uuid.uuid4()]
    )
    assert counts == {published.id: 1}
    assert set(thumbnails) == {published.id}


def test_signed_thumbnail_lookup_allows_shared_member():
    """Catches direct Moment ownership checks in signed thumbnail delivery."""
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    owner = _user(f"owner-{uuid.uuid4().hex}@example.com")
    reader = _user(f"reader-{uuid.uuid4().hex}@example.com")
    session.add_all([owner, reader])
    session.commit()
    journal = Journal(user_id=owner.id, title="Shared")
    moment = Moment(user_id=owner.id, logged_date_tz=date(2026, 9, 30))
    session.add_all([journal, moment])
    session.commit()
    media = MomentMedia(
        moment_id=moment.id,
        media_type=MediaType.IMAGE,
        file_path="images/shared.jpg",
        file_size=1,
        mime_type="image/jpeg",
        upload_status=UploadStatus.COMPLETED,
    )
    session.add_all([
        Entry(user_id=owner.id, journal_id=journal.id, moment_id=moment.id),
        media,
        JournalMember(
            journal_id=journal.id,
            user_id=reader.id,
            permission=JournalPermission.READONLY,
        ),
    ])
    session.commit()

    assert MediaService(session).get_media_by_id(media.id, reader.id, session) == media


def test_signed_media_lookup_hides_media_from_an_unrelated_user():
    """Catches an access lookup that returns a row before checking its Moment."""
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    owner = _user(f"owner-{uuid.uuid4().hex}@example.com")
    outsider = _user(f"outsider-{uuid.uuid4().hex}@example.com")
    session.add_all([owner, outsider])
    session.commit()
    moment = Moment(user_id=owner.id, logged_date_tz=date(2026, 9, 30))
    session.add(moment)
    session.commit()
    media = MomentMedia(
        moment_id=moment.id,
        media_type=MediaType.IMAGE,
        file_path="images/private.jpg",
        file_size=1,
        mime_type="image/jpeg",
        upload_status=UploadStatus.COMPLETED,
    )
    session.add(media)
    session.commit()

    with pytest.raises(MediaNotFoundError, match="Media not found"):
        MediaService(session).get_media_by_id(media.id, outsider.id, session)


def test_readonly_member_cannot_delete_shared_published_media():
    """Catches deletion using read permission instead of edit permission."""
    session, _, reader, journal, _ = _create_shared_draft_media()
    entry = session.exec(select(Entry).where(Entry.journal_id == journal.id)).one()
    entry.is_draft = False
    session.add(entry)
    session.commit()
    media = session.exec(select(MomentMedia).where(MomentMedia.moment_id == entry.moment_id)).one()

    with pytest.raises(MediaNotFoundError, match="Media not found"):
        MediaService(session).delete_media_by_id_sync(media.id, reader.id, session)

    assert session.get(MomentMedia, media.id) is not None


def test_entry_cannot_move_to_a_journal_owned_by_another_user():
    """Catches cross-owner moves that retain the former owner's durable access."""
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    owner = _user(f"owner-{uuid.uuid4().hex}@example.com")
    collaborator = _user(f"collaborator-{uuid.uuid4().hex}@example.com")
    session.add_all([owner, collaborator])
    session.commit()
    source = Journal(user_id=owner.id, title="Source")
    target = Journal(user_id=collaborator.id, title="Target")
    moment = Moment(user_id=owner.id, logged_date_tz=date(2026, 9, 30))
    session.add_all([source, target, moment])
    session.commit()
    entry = Entry(user_id=owner.id, journal_id=source.id, moment_id=moment.id)
    session.add_all([
        entry,
        JournalMember(
            journal_id=target.id,
            user_id=owner.id,
            permission=JournalPermission.EDIT,
        ),
    ])
    session.commit()

    with pytest.raises(JournalNotFoundError, match="Target journal not found"):
        EntryService(session).update_entry(
            entry.id, owner.id, EntryUpdate(journal_id=target.id)
        )

    assert session.get(Entry, entry.id).journal_id == source.id


@pytest.mark.parametrize(
    ("entry_type", "is_draft"),
    [(EntryCreate, False), (EntryDraftCreate, True)],
)
def test_edit_member_can_create_an_entry_in_a_shared_journal(entry_type, is_draft):
    """Editors can create draft and published entries from their own Moments in shared journals."""
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    owner = _user(f"owner-{uuid.uuid4().hex}@example.com")
    editor = _user(f"editor-{uuid.uuid4().hex}@example.com")
    session.add_all([owner, editor])
    session.commit()
    journal = Journal(user_id=owner.id, title="Shared")
    moment = Moment(user_id=editor.id, logged_date_tz=date(2026, 9, 30))
    session.add_all([journal, moment])
    session.commit()
    session.add(
        JournalMember(
            journal_id=journal.id,
            user_id=editor.id,
            permission=JournalPermission.EDIT,
        )
    )
    session.commit()

    entry = EntryService(session).create_entry(
        editor.id,
        entry_type(
            journal_id=journal.id,
            moment_id=moment.id,
            content_delta={"ops": [{"insert": "Shared writing\n"}]},
        ),
        is_draft=is_draft,
    )

    assert entry.user_id == owner.id
    assert entry.created_by_user_id == editor.id
    assert session.get(Moment, moment.id).user_id == owner.id
    assert session.get(Journal, journal.id).entry_count == (0 if is_draft else 1)


def test_shared_draft_author_can_access_media_and_recover_until_revoked():
    """Authors can access and recover shared drafts until membership is revoked."""
    session, owner, editor, journal = _create_shared_journal_for_actor("editor")
    moment = Moment(user_id=editor.id, logged_date_tz=date(2026, 9, 30))
    session.add(moment)
    session.commit()
    entry = EntryService(session).create_entry(
        editor.id, EntryDraftCreate(journal_id=journal.id, moment_id=moment.id), is_draft=True
    )
    assert get_accessible_moment(session, editor.id, moment.id, edit=True).id == moment.id
    assert MediaService(session)._get_moment_for_user(session, moment.id, editor.id).id == moment.id
    assert entry.id in {draft.id for draft in EntryService(session).get_user_drafts(editor.id)}
    member = session.exec(select(JournalMember).where(JournalMember.user_id == editor.id)).one()
    session.delete(member)
    session.commit()
    with pytest.raises(MomentNotFoundError):
        get_accessible_moment(session, editor.id, moment.id, edit=True)
    assert EntryService(session).get_user_drafts(editor.id) == []


def test_shared_draft_author_can_finalize_and_discard(monkeypatch):
    """Authors can finalize or discard their own shared drafts."""
    session, owner, editor, journal = _create_shared_journal_for_actor("editor")
    monkeypatch.setattr(EntryService, "_run_entry_side_effects", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.core.celery_app.celery_app.send_task", lambda *args, **kwargs: None)
    service = EntryService(session)
    for finalize in (True, False):
        moment = Moment(user_id=editor.id, logged_date_tz=date(2026, 9, 30))
        session.add(moment)
        session.commit()
        entry = service.create_entry(
            editor.id, EntryDraftCreate(journal_id=journal.id, moment_id=moment.id), is_draft=True
        )
        if finalize:
            assert not service.update_entry(entry.id, editor.id, EntryUpdate(is_draft=False)).is_draft
        else:
            moment_id = moment.id
            assert MomentService(session).delete_moment(moment_id, editor.id)["deleted"]
            assert session.get(Moment, moment_id) is None


def test_editor_draft_is_private_until_published(monkeypatch):
    """Only the author can read, list, edit, or delete an unfinished entry."""
    session, owner, editor, journal = _create_shared_journal_for_actor("editor")
    other = _user(f"other-{uuid.uuid4().hex}@example.com")
    session.add(other)
    session.commit()
    session.add(JournalMember(journal_id=journal.id, user_id=other.id, permission=JournalPermission.EDIT))
    moment = Moment(user_id=editor.id, logged_date_tz=date(2026, 9, 30))
    session.add(moment)
    session.commit()
    monkeypatch.setattr(EntryService, "_run_entry_side_effects", lambda *args, **kwargs: None)
    service = EntryService(session)
    entry = service.create_entry(
        editor.id, EntryDraftCreate(journal_id=journal.id, moment_id=moment.id), is_draft=True
    )
    media = MomentMedia(
        moment_id=moment.id, media_type=MediaType.IMAGE, file_path="images/draft.jpg",
        file_size=1, mime_type="image/jpeg", upload_status=UploadStatus.COMPLETED,
    )
    session.add(media)
    session.commit()
    for viewer in (owner, other):
        assert service.get_entry_by_id(entry.id, viewer.id) is None
        with pytest.raises(EntryNotFoundError):
            service.update_entry(entry.id, viewer.id, EntryUpdate(title="No"))
        with pytest.raises(MomentNotFoundError):
            get_accessible_moment(session, viewer.id, moment.id)
        with pytest.raises(MomentNotFoundError):
            MomentService(session).delete_moment(moment.id, viewer.id)
        with pytest.raises(MediaNotFoundError):
            MediaService(session).get_media_by_id(media.id, viewer.id, session)
        assert entry.id not in {item.id for item in service.get_user_drafts(viewer.id)}
        assert entry.id not in {item.id for item in service.get_user_entries(viewer.id, include_drafts=True)}
        assert entry.id not in {item.id for item in service.get_journal_entries(journal.id, viewer.id, include_drafts=True)}
        moments, _, _ = MomentService(session).get_moments(viewer.id, include_drafts=True)
        assert moment.id not in {item.id for item in moments}
        assert moment.id not in {item.id for item in MomentService(session).get_calendar_summary(viewer.id)}
        items, _, _ = MediaService(session).get_media_library(session, viewer.id, journal_id=journal.id)
        assert media.id not in {item.id for item in items}
    assert entry.id in {item.id for item in service.get_user_drafts(editor.id)}
    assert entry.id in {item.id for item in service.get_journal_entries(journal.id, editor.id, include_drafts=True)}
    moments, _, _ = MomentService(session).get_moments(editor.id, include_drafts=True)
    assert moment.id in {item.id for item in moments}
    moments, _, _ = MomentService(session).get_moments(editor.id)
    assert moment.id not in {item.id for item in moments}
    items, _, _ = MediaService(session).get_media_library(session, editor.id, journal_id=journal.id)
    assert media.id in {item.id for item in items}
    member = session.exec(select(JournalMember).where(JournalMember.user_id == editor.id)).one()
    member.permission = JournalPermission.READONLY
    session.add(member)
    session.commit()
    assert get_accessible_moment(session, editor.id, moment.id).id == moment.id
    with pytest.raises(MomentNotFoundError):
        get_accessible_moment(session, editor.id, moment.id, edit=True)
    with pytest.raises(MomentNotFoundError):
        MediaService(session)._get_moment_for_user(session, moment.id, editor.id)
    with pytest.raises(EntryNotFoundError):
        service.update_entry(entry.id, editor.id, EntryUpdate(is_draft=False))
    member.permission = JournalPermission.EDIT
    session.add(member)
    session.commit()
    service.update_entry(entry.id, editor.id, EntryUpdate(is_draft=False))
    for viewer in (owner, other):
        assert service.get_entry_by_id(entry.id, viewer.id) is not None
        assert get_accessible_moment(session, viewer.id, moment.id).id == moment.id


def test_shared_people_replacement_preserves_other_users_links():
    """Editors can change their own person tags without removing others' tags."""
    session, owner, editor, journal = _create_shared_journal_for_actor("editor")
    moment = Moment(user_id=owner.id, logged_date_tz=date(2026, 9, 30))
    owner_person = Person(user_id=owner.id, name="Owner person", normalized_name="owner person")
    editor_person = Person(user_id=editor.id, name="Editor person", normalized_name="editor person")
    session.add_all([moment, owner_person, editor_person])
    session.commit()
    session.add_all([
        Entry(user_id=owner.id, journal_id=journal.id, moment_id=moment.id),
        MomentPersonLink(moment_id=moment.id, person_id=owner_person.id),
    ])
    session.commit()
    service = PersonService(session)
    assert [p.id for p in service.replace_moment_people(moment.id, [owner_person.id, editor_person.id], editor.id)] == [editor_person.id]
    assert {link.person_id for link in session.exec(select(MomentPersonLink)).all()} == {owner_person.id, editor_person.id}
    service.replace_moment_people(moment.id, [], editor.id)
    assert {link.person_id for link in session.exec(select(MomentPersonLink)).all()} == {owner_person.id}
    member = session.exec(select(JournalMember).where(JournalMember.user_id == editor.id)).one()
    member.permission = JournalPermission.READONLY
    session.add(member)
    session.commit()
    with pytest.raises(MomentNotFoundError):
        service.replace_moment_people(moment.id, [editor_person.id], editor.id)


@pytest.mark.parametrize(
    ("actor", "is_draft", "allowed"),
    [
        ("owner", False, True),
        ("owner", True, True),
        ("editor", False, True),
        ("editor", True, True),
        ("reader", False, False),
        ("reader", True, False),
        ("outsider", False, False),
        ("outsider", True, False),
    ],
)
def test_shared_entry_creation_respects_member_permission(actor, is_draft, allowed):
    """Only owners and editors can create shared journal entries."""
    session, owner, actor_user, journal = _create_shared_journal_for_actor(actor)
    moment = Moment(
        user_id=actor_user.id if actor == "editor" else owner.id,
        logged_date_tz=date(2026, 9, 30),
    )
    session.add(moment)
    session.commit()
    entry_data = EntryCreate(
        journal_id=journal.id,
        moment_id=moment.id,
        content_delta={"ops": [{"insert": "Shared writing\n"}]},
    )

    if allowed:
        entry = EntryService(session).create_entry(actor_user.id, entry_data, is_draft=is_draft)

        assert entry.user_id == owner.id
        assert entry.created_by_user_id == actor_user.id
        assert session.get(Moment, moment.id).user_id == owner.id
        assert session.get(Journal, journal.id).entry_count == (0 if is_draft else 1)
    else:
        with pytest.raises(JournalNotFoundError, match="Journal not found"):
            EntryService(session).create_entry(actor_user.id, entry_data, is_draft=is_draft)

        assert session.exec(select(Entry).where(Entry.journal_id == journal.id)).first() is None
        assert session.get(Moment, moment.id).user_id == owner.id
        assert session.get(Journal, journal.id).entry_count == 0


def test_shared_media_cleanup_preserves_all_files_still_referenced(tmp_path: Path):
    """Catches cleanup deleting thumbnail variants before reference counting."""
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    owner = _user(f"owner-{uuid.uuid4().hex}@example.com")
    session.add(owner)
    session.commit()
    first_moment = Moment(user_id=owner.id, logged_date_tz=date(2026, 9, 30))
    second_moment = Moment(user_id=owner.id, logged_date_tz=date(2026, 10, 1))
    session.add_all([first_moment, second_moment])
    session.commit()
    checksum = "a" * 64
    first_media = MomentMedia(
        moment_id=first_moment.id,
        media_type=MediaType.IMAGE,
        file_path="images/shared.jpg",
        thumbnail_path="images/thumb.jpg",
        display_path="images/display.jpg",
        file_size=1,
        mime_type="image/jpeg",
        checksum=checksum,
    )
    second_media = MomentMedia(
        moment_id=second_moment.id,
        media_type=MediaType.IMAGE,
        file_path="images/shared.jpg",
        thumbnail_path="images/thumb.jpg",
        display_path="images/display.jpg",
        file_size=1,
        mime_type="image/jpeg",
        checksum=checksum,
    )
    session.add_all([first_media, second_media])
    session.commit()
    for relative_path in ("images/shared.jpg", "images/thumb.jpg", "images/display.jpg"):
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")

    session.delete(first_media)
    session.flush()
    service = MediaService(session)
    service.media_root = tmp_path
    service._delete_media_file_with_reference_count(
        owner.id,
        {
            "file_path": "images/shared.jpg",
            "thumbnail_path": "images/thumb.jpg",
            "display_path": "images/display.jpg",
            "checksum": checksum,
            "force": False,
        },
        session,
    )

    assert (tmp_path / "images/shared.jpg").exists()
    assert (tmp_path / "images/thumb.jpg").exists()
    assert (tmp_path / "images/display.jpg").exists()


def test_entry_response_uses_deleted_user_byline_when_creator_is_missing():
    """Catches author display falling back to an empty persisted snapshot."""
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    owner = _user(f"owner-{uuid.uuid4().hex}@example.com")
    session.add(owner)
    session.commit()
    journal = Journal(user_id=owner.id, title="Shared")
    moment = Moment(user_id=owner.id, logged_date_tz=date(2026, 9, 30))
    session.add_all([journal, moment])
    session.commit()
    entry = Entry(
        user_id=owner.id,
        journal_id=journal.id,
        moment_id=moment.id,
        created_by_user_id=None,
    )
    session.add(entry)
    session.commit()

    assert EntryResponse.model_validate(entry).author_name == "deleted user"


@pytest.mark.parametrize("permission", [JournalPermission.READONLY, JournalPermission.EDIT])
def test_shared_draft_media_lookup_hides_media_from_members(permission):
    """Journal membership never grants access to the owner's draft media."""
    session, _, member, _, media = _create_shared_draft_media(permission)

    with pytest.raises(MediaNotFoundError, match="Media not found"):
        MediaService(session).get_media_by_id(media.id, member.id, session)


@pytest.mark.parametrize("permission", [JournalPermission.READONLY, JournalPermission.EDIT])
def test_journal_media_library_hides_shared_draft_media_from_members(permission):
    """Journal membership never exposes the owner's draft media in the library."""
    session, _, member, journal, media = _create_shared_draft_media(permission)

    items, _, _ = MediaService(session).get_media_library(
        session, member.id, journal_id=journal.id
    )

    assert media.id not in [item.id for item in items]


def test_journal_analytics_includes_journals_shared_with_the_viewer():
    """Catches a regression to owner-only journal analytics queries."""
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    owner = _user(f"owner-{uuid.uuid4().hex}@example.com")
    reader = _user(f"reader-{uuid.uuid4().hex}@example.com")
    session.add_all([owner, reader])
    session.commit()
    journal = Journal(user_id=owner.id, title="Shared")
    moment = Moment(user_id=owner.id, logged_date_tz=date(2026, 9, 30))
    session.add_all([journal, moment])
    session.commit()
    session.add_all([
        Entry(user_id=owner.id, journal_id=journal.id, moment_id=moment.id),
        JournalMember(
            journal_id=journal.id,
            user_id=reader.id,
            permission=JournalPermission.READONLY,
        ),
    ])
    session.commit()

    analytics = AnalyticsService(session).get_journal_analytics(reader.id)

    assert [item["title"] for item in analytics["journals"]] == ["Shared"]
