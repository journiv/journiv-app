"""
Regression test: a 401/403 from Immich while proxying signed media did not
call `_update_integration_error_state` the way the dedicated proxy endpoints
(`app/integrations/router.py`) do, so Settings never learned the token was
bad and kept telling the user everything was fine.
"""
from contextlib import contextmanager
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlmodel import Session, create_engine

import app.api.v1.endpoints.media as media_module
import app.integrations.router as router_module
from app.models.base import BaseModel
from app.models.entry import Entry
from app.models.enums import JournalPermission, MediaType, UploadStatus
from app.models.journal import Journal
from app.models.journal_member import JournalMember
from app.models.moment import Moment, MomentMedia
from app.models.user import User
from app.services.media_service import MediaService


class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.headers = {}

    async def aclose(self):
        pass

    async def aiter_bytes(self):
        """Yield fake thumbnail bytes."""
        yield b"thumbnail"


@contextmanager
def _fake_session_context(*_args, **_kwargs):
    yield MagicMock()


@pytest.mark.asyncio
async def test_signed_original_401_updates_integration_error_state():
    media_id = uuid4()
    uid = uuid4()

    fake_media = MagicMock(external_provider="immich", external_asset_id="asset-1", file_path=None)
    fake_media_service = MagicMock()
    fake_media_service.get_media_by_id.return_value = fake_media
    fake_session = MagicMock()
    fake_session.get.return_value = MagicMock(user_id=uid)

    @contextmanager
    def fake_session_context(*_args, **_kwargs):
        """Provide the mocked database session."""
        yield fake_session

    with patch.object(media_module, "_get_media_service", return_value=fake_media_service), \
         patch.object(media_module, "is_signature_expired", return_value=False), \
         patch.object(media_module, "verify_media_signature", return_value=True), \
          patch.object(
              media_module.database_module, "get_session_context", side_effect=fake_session_context
         ), \
         patch.object(
             media_module, "fetch_proxy_asset", new=AsyncMock(return_value=_FakeResponse(401))
         ), \
         patch.object(
             router_module, "_update_integration_error_state", new=AsyncMock()
         ) as mock_update_error_state:
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await media_module.get_media_signed(
                media_id=media_id, uid=uid, exp=9999999999, sig="sig"
            )

    assert exc_info.value.status_code == 401
    mock_update_error_state.assert_called_once()
    call_args = mock_update_error_state.call_args.args
    assert call_args[0] == uid


@pytest.mark.asyncio
async def test_signed_shared_immich_thumbnail_uses_moment_owner_credentials():
    """Fetch shared Immich thumbnails using the owner's credentials."""
    media_id = uuid4()
    viewer_id = uuid4()
    owner_id = uuid4()
    fake_media = MagicMock(
        external_provider="immich",
        external_asset_id="asset-1",
        thumbnail_path=None,
        moment_id=uuid4(),
    )
    fake_media_service = MagicMock()
    fake_media_service.get_media_by_id.return_value = fake_media
    fake_session = MagicMock()
    fake_session.get.return_value = MagicMock(user_id=owner_id)

    @contextmanager
    def fake_session_context(*_args, **_kwargs):
        """Provide the mocked database session."""
        yield fake_session

    with patch.object(media_module, "_get_media_service", return_value=fake_media_service), \
         patch.object(media_module, "is_signature_expired", return_value=False), \
         patch.object(media_module, "verify_media_signature", return_value=True), \
         patch.object(
             media_module.database_module, "get_session_context", side_effect=fake_session_context
         ), \
         patch.object(
             media_module, "fetch_proxy_asset", new=AsyncMock(return_value=_FakeResponse(200))
         ) as mock_fetch:
        await media_module.get_media_thumbnail_signed(
            media_id=media_id, uid=viewer_id, exp=9999999999, sig="sig"
        )

    assert mock_fetch.await_args.kwargs["user_id"] == owner_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "permission", "is_member"),
    [
        ("original", JournalPermission.READONLY, True),
        ("thumbnail", JournalPermission.READONLY, True),
        ("original", JournalPermission.EDIT, True),
        ("thumbnail", JournalPermission.EDIT, True),
        ("original", JournalPermission.READONLY, False),
        ("thumbnail", JournalPermission.READONLY, False),
    ],
)
async def test_signed_media_denies_shared_drafts_before_serving(endpoint, permission, is_member):
    """Signed endpoints must apply the real viewer policy before serving a draft."""
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    owner = User(email=f"owner-{uuid4().hex}@example.com", password="password", name="owner")
    reader = User(email=f"reader-{uuid4().hex}@example.com", password="password", name="reader")
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
    session.add_all([Entry(user_id=owner.id, journal_id=journal.id, moment_id=moment.id, is_draft=True), media])
    if is_member:
        session.add(JournalMember(journal_id=journal.id, user_id=reader.id, permission=permission))
    session.commit()
    media_service = MediaService(session)

    @contextmanager
    def fake_session_context(*_args, **_kwargs):
        """Provide the database session containing the shared draft."""
        yield session

    with patch.object(media_module, "_get_media_service", return_value=media_service), \
         patch.object(media_module, "is_signature_expired", return_value=False), \
          patch.object(media_module, "verify_media_signature", return_value=True), \
          patch.object(
              media_module.database_module, "get_session_context", side_effect=fake_session_context
          ), \
          patch.object(media_service, "get_media_by_id", wraps=media_service.get_media_by_id) as lookup, \
          patch.object(media_module, "fetch_proxy_asset", new=AsyncMock()) as fetch_proxy:
        with pytest.raises(HTTPException) as exc_info:
            if endpoint == "original":
                await media_module.get_media_signed(
                    media_id=media.id, uid=reader.id, exp=9999999999, sig="sig"
                )
            else:
                await media_module.get_media_thumbnail_signed(
                    media_id=media.id, uid=reader.id, exp=9999999999, sig="sig"
                )

    assert lookup.call_args.args == (media.id, reader.id, session)
    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail.lower()
    fetch_proxy.assert_not_awaited()
