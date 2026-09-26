"""
Regression tests: copy imports are never post-processed.

`_download_and_save_original` used to upsert the row as COMPLETED and then
call `media_service.process_uploaded_file`, which returns immediately for an
already-COMPLETED row (its own duplicate-upload guard). So for every copy
import: metadata extraction never ran, no fallback thumbnail was generated
when the Immich thumbnail download had failed, and no local HEIC display
version was made when the Immich preview download had failed. The row is now
upserted PROCESSING, letting `process_uploaded_file` do its normal work and
set the row COMPLETED (or FAILED) itself.
"""
import io
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from app.core.encryption import encrypt_token
from app.models.base import BaseModel
from app.models.enums import MediaType, UploadStatus
from app.models.integration import ImportMode, Integration, IntegrationProvider
from app.models.moment import Moment, MomentMedia
from app.models.user import User
from app.services import media_service as media_service_module
from app.services.import_job_service import ImportJobService


def _setup_session() -> Session:
    # One shared in-memory database across threads, as app/core/database.py
    # configures it: post-processing runs in a worker thread.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    BaseModel.metadata.create_all(engine)
    return Session(engine)


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


def _create_integration(session: Session, user_id: uuid.UUID) -> Integration:
    integration = Integration(
        user_id=user_id,
        provider=IntegrationProvider.IMMICH,
        base_url="http://immich.test",
        access_token_encrypted=encrypt_token("fake-api-key"),
        external_user_id="immich-user-1",
        is_active=True,
        import_mode=ImportMode.COPY,
    )
    session.add(integration)
    session.commit()
    session.refresh(integration)
    return integration


def _create_placeholder(session: Session, moment_id: uuid.UUID, asset_id: str) -> MomentMedia:
    media = MomentMedia(
        moment_id=moment_id,
        media_type=MediaType.IMAGE,
        mime_type="application/octet-stream",
        upload_status=UploadStatus.PROCESSING,
        external_provider="immich",
        external_asset_id=asset_id,
    )
    session.add(media)
    session.commit()
    session.refresh(media)
    return media


def _valid_jpeg_bytes() -> bytes:
    image = Image.new("RGB", (1, 1), color=(255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


class _FakeStreamResponse:
    def __init__(self, content: bytes):
        self.status_code = 200
        self._content = content

    async def aiter_bytes(self):
        yield self._content


class _FakeStreamCtx:
    def __init__(self, content: bytes):
        self._content = content

    async def __aenter__(self):
        return _FakeStreamResponse(self._content)

    async def __aexit__(self, *args):
        return False


class _FakeClient:
    def __init__(self, content: bytes):
        self._content = content

    def stream(self, method, url, headers=None, timeout=None):
        return _FakeStreamCtx(self._content)


@pytest.mark.asyncio
async def test_download_and_save_original_upserts_processing_not_completed():
    """
    The exact bug: upserting COMPLETED before calling process_uploaded_file
    made it a no-op. Mocking process_uploaded_file and inspecting the row
    right after the upsert shows what status it was actually given.
    """
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    integration = _create_integration(session, user.id)
    asset_id = "asset-1"
    _create_placeholder(session, moment.id, asset_id)

    asset_metadata = {
        "id": asset_id,
        "type": "IMAGE",
        "originalFileName": "photo.jpg",
        "mimeType": "image/jpeg",
    }
    saved_info = {
        "filename": "stored.jpg",
        "file_path": "images/stored.jpg",
        "full_file_path": "/tmp/does-not-matter.jpg",
        "original_filename": "photo.jpg",
        "file_size": 1024,
        "mime_type": "image/jpeg",
        "checksum": "abc123",
    }

    with patch(
        "app.services.import_job_service.immich.get_asset_info",
        new=AsyncMock(return_value=asset_metadata),
    ), patch(
        "app.services.import_job_service.get_http_client",
        new=AsyncMock(return_value=_FakeClient(b"irrelevant-bytes")),
    ):
        service = ImportJobService(session)
        with patch.object(
            service.media_service, "save_uploaded_file", new=AsyncMock(return_value=saved_info)
        ), patch.object(
            service.media_service, "process_uploaded_file"
        ) as mock_process:
            result = await service._download_and_save_original(
                asset_id=asset_id,
                base_url=integration.base_url,
                api_key="key",
                user_id=str(user.id),
                moment_id=moment.id,
                integration=integration,
                session=session,
                thumbnail_info=None,
                commit=True,
            )

    # The mock leaves the row PROCESSING. The copy must not be counted as a
    # successful import without a completed post-processing outcome.
    assert result is None
    mock_process.assert_called_once()
    call_kwargs = mock_process.call_args.kwargs
    assert call_kwargs["file_path"] == saved_info["full_file_path"]

    session.expire_all()
    media = session.exec(
        select(MomentMedia).where(MomentMedia.external_asset_id == asset_id)
    ).first()
    # Upserted PROCESSING (not COMPLETED): process_uploaded_file above was
    # mocked, so nothing else could have set this.
    assert media.upload_status == UploadStatus.PROCESSING


@pytest.mark.asyncio
async def test_post_processing_failure_is_not_counted_as_copy_success():
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    integration = _create_integration(session, user.id)
    _create_placeholder(session, moment.id, "asset-failed")
    asset_metadata = {
        "id": "asset-failed", "type": "IMAGE",
        "originalFileName": "photo.jpg", "mimeType": "image/jpeg",
    }
    saved_info = {
        "file_path": "images/stored.jpg", "full_file_path": "/tmp/unused.jpg",
        "original_filename": "photo.jpg", "file_size": 1024,
        "mime_type": "image/jpeg", "checksum": "failure-checksum",
    }

    def fail_processing(**kwargs):
        media = session.get(MomentMedia, uuid.UUID(kwargs["media_id"]))
        media.upload_status = UploadStatus.FAILED
        session.add(media)
        session.commit()

    with patch(
        "app.services.import_job_service.immich.get_asset_info",
        new=AsyncMock(return_value=asset_metadata),
    ), patch(
        "app.services.import_job_service.get_http_client",
        new=AsyncMock(return_value=_FakeClient(b"irrelevant-bytes")),
    ):
        service = ImportJobService(session)
        with patch.object(
            service.media_service, "save_uploaded_file", new=AsyncMock(return_value=saved_info)
        ), patch.object(
            service.media_service, "process_uploaded_file", side_effect=fail_processing
        ):
            result = await service._download_and_save_original(
                asset_id="asset-failed", base_url=integration.base_url, api_key="key",
                user_id=str(user.id), moment_id=moment.id,
                integration=integration, session=session, commit=True,
            )

    assert result is None
    media = session.exec(
        select(MomentMedia).where(MomentMedia.external_asset_id == "asset-failed")
    ).one()
    assert media.upload_status == UploadStatus.FAILED


@pytest.mark.asyncio
async def test_copy_import_actually_post_processes_end_to_end(tmp_path):
    """
    Full pipeline, nothing mocked past the network: process_uploaded_file
    must genuinely run — extracting metadata and generating a fallback
    thumbnail from the locally-saved original — and the row must reach
    COMPLETED, not get silently skipped.
    """
    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    integration = _create_integration(session, user.id)
    asset_id = "asset-2"
    _create_placeholder(session, moment.id, asset_id)

    asset_metadata = {
        "id": asset_id,
        "type": "IMAGE",
        "originalFileName": "photo.jpg",
        "mimeType": "image/jpeg",
    }
    jpeg_bytes = _valid_jpeg_bytes()

    with patch.object(
        media_service_module.settings, "media_root", str(tmp_path / "media")
    ), patch(
        "app.services.import_job_service.immich.get_asset_info",
        new=AsyncMock(return_value=asset_metadata),
    ), patch(
        "app.services.import_job_service.get_http_client",
        new=AsyncMock(return_value=_FakeClient(jpeg_bytes)),
    ):
        service = ImportJobService(session)
        result = await service._download_and_save_original(
            asset_id=asset_id,
            base_url=integration.base_url,
            api_key="key",
            user_id=str(user.id),
            moment_id=moment.id,
            integration=integration,
            session=session,
            # No Immich thumbnail: process_uploaded_file's own fallback
            # thumbnail generation, from the locally-saved original, is the
            # only thing that can produce one.
            thumbnail_info=None,
            commit=True,
        )

    assert result is not None
    session.expire_all()
    media = session.exec(
        select(MomentMedia).where(MomentMedia.external_asset_id == asset_id)
    ).first()
    assert media.upload_status == UploadStatus.COMPLETED
    assert media.width == 1
    assert media.height == 1
    assert media.thumbnail_path is not None


@pytest.mark.asyncio
async def test_post_processing_runs_off_the_event_loop_thread():
    """process_uploaded_file is synchronous, heavy work (thumbnails, HEIC,
    video frames). On the shared import loop it blocked every other job."""
    import threading

    session = _setup_session()
    user = _create_user(session)
    moment = _create_moment(session, user.id)
    integration = _create_integration(session, user.id)
    _create_placeholder(session, moment.id, "asset-3")
    saved_info = {
        "filename": "stored.jpg",
        "file_path": "images/stored.jpg",
        "full_file_path": "/tmp/does-not-matter.jpg",
        "original_filename": "photo.jpg",
        "file_size": 1024,
        "mime_type": "image/jpeg",
        "checksum": "abc123",
    }
    loop_thread = threading.get_ident()
    ran_on: list[int] = []

    with patch(
        "app.services.import_job_service.immich.get_asset_info",
        new=AsyncMock(return_value={"id": "asset-3", "type": "IMAGE", "originalFileName": "photo.jpg"}),
    ), patch(
        "app.services.import_job_service.get_http_client",
        new=AsyncMock(return_value=_FakeClient(b"irrelevant-bytes")),
    ):
        service = ImportJobService(session)
        with patch.object(
            service.media_service, "save_uploaded_file", new=AsyncMock(return_value=saved_info)
        ), patch.object(
            service.media_service,
            "process_uploaded_file",
            side_effect=lambda **_kwargs: ran_on.append(threading.get_ident()),
        ):
            await service._download_and_save_original(
                asset_id="asset-3",
                base_url=integration.base_url,
                api_key="key",
                user_id=str(user.id),
                moment_id=moment.id,
                integration=integration,
                session=session,
                thumbnail_info=None,
                commit=True,
            )

    assert len(ran_on) == 1
    assert ran_on[0] != loop_thread
