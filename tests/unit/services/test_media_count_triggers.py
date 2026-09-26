"""
Regression tests for media_count being decremented twice on media delete.

Production databases have moment_media DELETE triggers (installed by
alembic/versions/aa9a7125186b_add_activities_moods_goals_moments.py) that
decrement `moment.media_count`. `MediaService.delete_orphaned_media_for_delta`
and `MediaService.delete_media_by_id_sync` also decremented it by hand, so a
moment with 2 media ended up with media_count = 0 after deleting just 1 (the
trigger takes it 2 -> 1, the manual update then takes it 1 -> 0). The React
reader and timeline hide a moment once media_count reaches 0, so the
remaining photo disappeared.

Unit tests build schemas with `create_all` and get no triggers, so these
tests install the same trigger SQL directly (mirroring the migration's
SQLite trigger bodies, targeted at the model's current `moment_media` table
name) rather than relying on a real migrated database.
"""
import uuid
from unittest.mock import patch

from sqlalchemy import text
from sqlmodel import Session, create_engine, select

from app.models.base import BaseModel
from app.models.enums import MediaType, UploadStatus
from app.models.moment import Moment, MomentMedia
from app.models.user import User
from app.services.media_service import MediaService

_TRIGGER_SQL = [
    """
    CREATE TRIGGER moment_media_count_insert_trigger
    AFTER INSERT ON moment_media
    FOR EACH ROW
    BEGIN
        UPDATE moment
        SET media_count = media_count + 1
        WHERE id = NEW.moment_id;
    END;
    """,
    """
    CREATE TRIGGER moment_media_count_delete_trigger
    AFTER DELETE ON moment_media
    FOR EACH ROW
    BEGIN
        UPDATE moment
        SET media_count = MAX(media_count - 1, 0)
        WHERE id = OLD.moment_id;
    END;
    """,
]


def _setup_session_with_triggers() -> Session:
    """In-memory SQLite session with the same media_count triggers production has."""
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    for statement in _TRIGGER_SQL:
        session.exec(text(statement))
    session.commit()
    return session


def _create_user(session: Session) -> User:
    user = User(email=f"test_{uuid.uuid4().hex[:8]}@example.com", password="hashed", name="Test User")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _create_moment(session: Session, user_id: uuid.UUID) -> Moment:
    moment = Moment(user_id=user_id)
    session.add(moment)
    session.commit()
    session.refresh(moment)
    return moment


def _create_media(session: Session, moment_id: uuid.UUID) -> MomentMedia:
    """Adding a row fires the insert trigger, so media_count tracks it exactly
    like it would against the real, migrated schema."""
    media = MomentMedia(
        moment_id=moment_id,
        media_type=MediaType.IMAGE,
        mime_type="image/jpeg",
        upload_status=UploadStatus.COMPLETED,
        file_path=f"media/{uuid.uuid4().hex}.jpg",
        file_size=1024,
    )
    session.add(media)
    session.commit()
    session.refresh(media)
    return media


def test_delete_media_by_id_sync_does_not_double_decrement():
    session = _setup_session_with_triggers()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    media_a = _create_media(session, moment.id)
    _create_media(session, moment.id)

    session.refresh(moment)
    assert moment.media_count == 2

    service = MediaService(session=session)
    # File/Celery cleanup is a documented no-op-on-failure side effect,
    # irrelevant to media_count; stub it out so the test stays hermetic.
    with patch.object(MediaService, "delete_media_files_post_commit"):
        service.delete_media_by_id_sync(media_a.id, user.id, session=session)

    session.expire_all()
    refreshed = session.get(Moment, moment.id)
    remaining = session.exec(
        select(MomentMedia).where(MomentMedia.moment_id == moment.id)
    ).all()
    assert len(remaining) == 1
    assert refreshed.media_count == 1


def test_delete_orphaned_media_for_delta_does_not_double_decrement():
    session = _setup_session_with_triggers()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    media_a = _create_media(session, moment.id)
    media_b = _create_media(session, moment.id)

    session.refresh(moment)
    assert moment.media_count == 2

    old_delta = {"ops": [
        {"insert": {"image": str(media_a.id)}},
        {"insert": {"image": str(media_b.id)}},
    ]}
    new_delta = {"ops": [
        {"insert": {"image": str(media_b.id)}},
    ]}

    service = MediaService(session=session)
    service.delete_orphaned_media_for_delta(
        moment.id, user.id, old_delta, new_delta, session=session
    )
    session.commit()

    session.expire_all()
    refreshed = session.get(Moment, moment.id)
    remaining = session.exec(
        select(MomentMedia).where(MomentMedia.moment_id == moment.id)
    ).all()
    assert len(remaining) == 1
    assert refreshed.media_count == 1


def test_delete_media_by_id_sync_never_goes_negative():
    """Deleting the last media leaves media_count at 0, not negative."""
    session = _setup_session_with_triggers()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    media_a = _create_media(session, moment.id)

    service = MediaService(session=session)
    with patch.object(MediaService, "delete_media_files_post_commit"):
        service.delete_media_by_id_sync(media_a.id, user.id, session=session)

    session.expire_all()
    refreshed = session.get(Moment, moment.id)
    assert refreshed.media_count == 0


def test_recount_writes_even_when_the_loaded_moment_looks_right():
    """
    Already-drifted data (the double decrement left media_count at 1 with 2
    rows). The Moment is loaded in the session while the delete trigger moves
    the stored count to 0; the true count is 1, which equals the stale
    in-session value, so a compare-then-write recount skipped the write.
    """
    session = _setup_session_with_triggers()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    media_a = _create_media(session, moment.id)
    _create_media(session, moment.id)
    session.exec(text(f"UPDATE moment SET media_count = 1 WHERE id = '{moment.id.hex}'"))
    session.commit()
    session.expire_all()
    assert session.get(Moment, moment.id).media_count == 1  # loaded, drifted

    with patch.object(MediaService, "delete_media_files_post_commit"):
        MediaService(session=session).delete_media_by_id_sync(
            media_a.id, user.id, session=session
        )

    stored = session.exec(
        text(f"SELECT media_count FROM moment WHERE id = '{moment.id.hex}'")
    ).one()[0]
    assert stored == 1
