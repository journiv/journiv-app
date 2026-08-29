"""
Entry creation must normalize Delta media references to bare media IDs.

A client may send a hydrated signed URL (the form the API returns on read).
If creation stored that verbatim, an expiring, user-scoped signature would
become permanent journal content, and `import_service.replace_media_ids` — which
remaps by exact ID only — could not restore the reference from a backup.
`update_entry` has always normalized; `create_entry` did not.
"""
import uuid

from sqlmodel import Session, create_engine

from app.models.base import BaseModel
from app.models.enums import MediaType, UploadStatus
from app.models.journal import Journal
from app.models.moment import Moment, MomentMedia
from app.models.user import User
from app.schemas.entry import EntryCreate, QuillDelta
from app.services.entry_service import EntryService


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    return Session(engine)


def _fixtures(session: Session):
    user = User(email=f"t_{uuid.uuid4().hex[:8]}@example.com", password="x", name="T")
    session.add(user)
    session.commit()
    session.refresh(user)

    journal = Journal(user_id=user.id, title="J")
    moment = Moment(user_id=user.id)
    session.add(journal)
    session.add(moment)
    session.commit()
    session.refresh(journal)
    session.refresh(moment)

    media = MomentMedia(
        moment_id=moment.id,
        media_type=MediaType.IMAGE,
        file_path=f"user/{user.id}/images/photo.jpg",
        original_filename="photo.jpg",
        file_size=1024,
        mime_type="image/jpeg",
        upload_status=UploadStatus.COMPLETED,
    )
    session.add(media)
    session.commit()
    session.refresh(media)
    return user, journal, moment, media


def _create(session, user, journal, moment, source: str):
    service = EntryService(session)
    entry = service.create_entry(
        user.id,
        EntryCreate(
            title="With media",
            journal_id=journal.id,
            moment_id=moment.id,
            content_delta=QuillDelta(
                ops=[{"insert": "before\n"}, {"insert": {"image": source}}, {"insert": "\n"}]
            ),
        ),
    )
    session.refresh(entry)
    return entry


def test_create_entry_normalizes_signed_url_to_media_id():
    session = _session()
    user, journal, moment, media = _fixtures(session)

    signed = f"/api/v1/media/{media.id}/signed?uid={user.id}&exp=1787786388&sig=deadbeef"
    entry = _create(session, user, journal, moment, signed)

    embed = entry.content_delta["ops"][1]["insert"]
    assert embed == {"image": str(media.id)}, "signed URL must not be persisted"
    assert "sig=" not in str(entry.content_delta)
    assert "exp=" not in str(entry.content_delta)


def test_create_entry_leaves_a_bare_media_id_untouched():
    session = _session()
    user, journal, moment, media = _fixtures(session)

    entry = _create(session, user, journal, moment, str(media.id))

    assert entry.content_delta["ops"][1]["insert"] == {"image": str(media.id)}


def test_create_entry_without_media_is_unchanged():
    session = _session()
    user, journal, moment, _ = _fixtures(session)

    service = EntryService(session)
    entry = service.create_entry(
        user.id,
        EntryCreate(
            title="Plain",
            journal_id=journal.id,
            moment_id=moment.id,
            content_delta=QuillDelta(ops=[{"insert": "just text\n"}]),
        ),
    )
    session.refresh(entry)

    assert entry.content_delta == {"ops": [{"insert": "just text\n", "attributes": None}]}
    assert entry.content_plain_text == "just text\n"
    assert entry.word_count == 2
