"""
Unit tests for MediaService upload streaming behavior.
"""
from io import BytesIO
from datetime import date
from pathlib import Path
import uuid

import pytest
from fastapi import UploadFile
from sqlmodel import Session, create_engine

from app.models.base import BaseModel
from app.models.entry import Entry
from app.models.enums import JournalColor
from app.models.journal import Journal
from app.models.user import User
from app.services import media_service as media_service_module
from app.services.media_service import MediaService
from app.services.media_storage_service import MediaStorageService


def _sample_jpeg_bytes() -> bytes:
    return (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07"
        b"\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01"
        b"\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        b"\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00?\x00\xff\xd9"
    )


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


@pytest.fixture
def test_user(test_db: Session) -> User:
    user = User(
        email=f"test_{uuid.uuid4().hex[:8]}@example.com",
        password="hashed_password",
        name="Test User",
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def test_entry(test_db: Session, test_user: User) -> Entry:
    journal = Journal(
        user_id=test_user.id,
        title="Test Journal",
        color=JournalColor.BLUE,
    )
    test_db.add(journal)
    test_db.commit()
    test_db.refresh(journal)

    entry = Entry(
        journal_id=journal.id,
        user_id=test_user.id,
        title="Entry",
        content_delta={"ops": [{"insert": "Test content\n"}]},
        content_plain_text="Test content",
        word_count=2,
        entry_date=date.today(),
    )
    test_db.add(entry)
    test_db.commit()
    test_db.refresh(entry)
    return entry


def _build_service(tmp_path: Path, session: Session) -> MediaService:
    media_root = tmp_path / "media"
    media_root.mkdir()
    media_service_module.settings.media_root = str(media_root)
    service = MediaService(session=session)
    service.media_root = media_root
    service.media_storage_service = MediaStorageService(media_root, session)
    return service


@pytest.mark.asyncio
async def test_save_uploaded_file_supports_stream(tmp_path, test_db):
    service = _build_service(tmp_path, test_db)
    payload = _sample_jpeg_bytes()
    stream = BytesIO(payload)

    media_info = await service.save_uploaded_file(
        original_filename="stream.jpg",
        user_id=str(uuid.uuid4()),
        media_type="image",
        file_stream=stream,
        file_size_override=len(payload),
        mime_type_override="image/jpeg",
    )

    full_path = service.media_storage_service.get_full_path(media_info["file_path"])
    assert full_path.exists()
    assert media_info["file_size"] == len(payload)
    assert media_info["mime_type"] == "image/jpeg"


@pytest.mark.asyncio
async def test_save_uploaded_file_rejects_non_seekable_stream(tmp_path, test_db):
    service = _build_service(tmp_path, test_db)

    class NonSeekableStream(BytesIO):
        def seekable(self):
            return False

        def seek(self, *_args, **_kwargs):
            raise OSError("not seekable")

    stream = NonSeekableStream(_sample_jpeg_bytes())

    with pytest.raises(ValueError):
        await service.save_uploaded_file(
            original_filename="stream.jpg",
            user_id=str(uuid.uuid4()),
            media_type="image",
            file_stream=stream,
        )


@pytest.mark.asyncio
async def test_upload_media_uses_streaming_path(tmp_path, test_db, test_user, test_entry, monkeypatch):
    service = _build_service(tmp_path, test_db)
    payload = _sample_jpeg_bytes()
    upload = UploadFile(filename="upload.jpg", file=BytesIO(payload))

    def _reject_tempfile(*_args, **_kwargs):
        raise AssertionError("tempfile fallback should not be used for seekable streams")

    monkeypatch.setattr("app.services.media_service.tempfile.NamedTemporaryFile", _reject_tempfile)

    # Patch get_session_context to use the test database session
    from contextlib import contextmanager

    @contextmanager
    def mock_session_context():
        yield test_db

    monkeypatch.setattr("app.services.media_service.get_session_context", mock_session_context)

    result = await service.upload_media(
        file=upload,
        user_id=test_user.id,
        entry_id=test_entry.id,
        session=test_db,
    )

    media_record = result["media_record"]
    assert media_record.entry_id == test_entry.id
