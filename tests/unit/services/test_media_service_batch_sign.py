import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.models.enums import MediaType, UploadStatus
from app.services import media_service as media_service_module
from app.services.media_service import MediaService
from app.services.media_storage_service import MediaStorageService
from app.schemas.media import MediaBatchSignRequest, MediaBatchSignItem


def _build_service(tmp_path: Path) -> MediaService:
    """Helper to build MediaService with temporary media root for testing."""
    media_root = tmp_path / "media"
    media_root.mkdir()

    # Use patch.object to temporarily change the setting during service initialization
    # and service-specific attribute assignments.
    with patch.object(media_service_module.settings, "media_root", str(media_root)):
        service = MediaService()
        service.media_root = media_root
        service.media_storage_service = MediaStorageService(media_root, None)
        return service


@pytest.mark.asyncio
async def test_batch_sign_local_media_success(tmp_path):
    media_id = uuid.uuid4()
    user_id = uuid.uuid4()

    session = MagicMock()
    rows = [
        (
            media_id,
            UploadStatus.COMPLETED,
            None,
            None,
            "/data/media/file.jpg",
            "/data/media/thumb.jpg",
            MediaType.IMAGE,
        )
    ]
    session.exec.return_value.all.return_value = rows

    service = _build_service(tmp_path)
    request = MediaBatchSignRequest(items=[MediaBatchSignItem(id=str(media_id), variant="original")])

    with patch("app.services.media_service.signed_url_for_journiv", return_value="signed-url"):
        response = await service.batch_sign_media(request, user_id, session)

    assert not response.errors
    assert response.results[0].signed_url == "signed-url"
    assert response.results[0].id == str(media_id)


@pytest.mark.asyncio
async def test_batch_sign_immich_integration_inactive(tmp_path):
    media_id = uuid.uuid4()
    asset_id = str(uuid.uuid4())
    user_id = uuid.uuid4()

    session = MagicMock()
    session.exec.side_effect = [
        MagicMock(
            all=MagicMock(
                return_value=[
                    (
                        media_id,
                        UploadStatus.COMPLETED,
                        "immich",
                        asset_id,
                        None,
                        None,
                        MediaType.IMAGE,
                    )
                ]
            )
        ),
        MagicMock(first=MagicMock(return_value=None)),
    ]

    service = _build_service(tmp_path)
    request = MediaBatchSignRequest(items=[MediaBatchSignItem(id=asset_id, variant="original")])

    response = await service.batch_sign_media(request, user_id, session)

    assert not response.results
    assert response.errors
    assert response.errors[0].error == "Immich integration not active"


@pytest.mark.asyncio
async def test_batch_sign_thumbnail_missing(tmp_path):
    media_id = uuid.uuid4()
    user_id = uuid.uuid4()

    session = MagicMock()
    session.exec.return_value.all.return_value = [
        (
            media_id,
            UploadStatus.COMPLETED,
            None,
            None,
            "/data/media/file.jpg",
            None,
            MediaType.IMAGE,
        )
    ]

    service = _build_service(tmp_path)
    request = MediaBatchSignRequest(items=[MediaBatchSignItem(id=str(media_id), variant="thumbnail")])

    response = await service.batch_sign_media(request, user_id, session)

    assert not response.results
    assert response.errors
    assert response.errors[0].error == "Thumbnail not available"
