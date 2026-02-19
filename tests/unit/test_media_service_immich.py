
import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session

from app.models.enums import MediaType, UploadStatus
from app.models.integration import Integration, IntegrationProvider
from app.schemas.media import MediaBatchSignItem, MediaBatchSignRequest
from app.services.media_service import MediaService


@pytest.fixture
def mock_session():
    return MagicMock(spec=Session)

@pytest.fixture
def mock_settings():
    with patch("app.services.media_service.settings") as mock:
        mock.media_signed_url_ttl_seconds = 3600
        mock.media_thumbnail_signed_url_ttl_seconds = 3600
        yield mock

@pytest.fixture
def media_service(mock_session, mock_settings):
    service = MediaService(session=mock_session)
    # Mock settings on the service instance directly as well since it might be accessed there
    service.settings = mock_settings
    return service

@pytest.fixture
def user_id():
    return uuid.uuid4()

@pytest.fixture
def entry_id():
    return uuid.uuid4()

@pytest.fixture
def active_immich_integration(user_id):
    integration = Integration(
        user_id=user_id,
        provider=IntegrationProvider.IMMICH,
        base_url="http://immich.test",
        access_token_encrypted="encrypted",
        external_user_id="immich-user",
        is_active=True
    )
    return integration

def create_mock_media(
    media_id, entry_id, user_id,
    provider="immich",
    asset_id="asset-1",
    status=UploadStatus.COMPLETED,
    file_path=None,
    thumbnail_path=None,
    media_type=MediaType.IMAGE
):
    # Determine what select().all() should return
    # Query in batch_sign_media returns tuple:
    # (id, upload_status, external_provider, external_asset_id, file_path, thumbnail_path, media_type)
    return (
        media_id,
        status,
        provider,
        asset_id,
        file_path,
        thumbnail_path,
        media_type
    )

@pytest.mark.asyncio
async def test_batch_sign_immich_link_only_success(
    media_service, mock_session, user_id, entry_id, active_immich_integration
):
    """Test signing for Immich Link-Only media (completed, no file path)."""
    media_id = uuid.uuid4()

    # Mock database response for media
    # Link-only: provider=immich, asset_id=set, file_path=None, status=COMPLETED
    mock_row = create_mock_media(
        media_id, entry_id, user_id,
        provider="immich",
        asset_id="asset-link-only",
        status=UploadStatus.COMPLETED,
        file_path=None,
        thumbnail_path=None
    )

    # Setup session mocks
    mock_session.exec.return_value.all.return_value = [mock_row]
    # Mock integration query
    mock_session.exec.return_value.first.return_value = active_immich_integration

    # Request
    request = MediaBatchSignRequest(items=[
        MediaBatchSignItem(id=str(media_id), variant="original")
    ])

    # Execute
    with patch("app.services.media_service.signed_url_for_journiv") as mock_sign:
        mock_sign.return_value = "signed-url"
        response = await media_service.batch_sign_media(request, user_id, mock_session)

    # Verify
    assert len(response.results) == 1
    assert len(response.errors) == 0
    assert response.results[0].id == str(media_id)
    assert response.results[0].signed_url == "signed-url"

@pytest.mark.asyncio
async def test_batch_sign_immich_link_only_processing(
    media_service, mock_session, user_id, entry_id, active_immich_integration
):
    """Test signing for Immich Link-Only media that is still processing."""
    media_id = uuid.uuid4()

    # Link-only placeholder: status=PROCESSING
    mock_row = create_mock_media(
        media_id, entry_id, user_id,
        provider="immich",
        asset_id="asset-link-only-pending",
        status=UploadStatus.PROCESSING,
        file_path=None
    )

    mock_session.exec.return_value.all.return_value = [mock_row]
    mock_session.exec.return_value.first.return_value = active_immich_integration

    request = MediaBatchSignRequest(items=[
        MediaBatchSignItem(id=str(media_id), variant="original")
    ])

    response = await media_service.batch_sign_media(request, user_id, mock_session)

    # Verify error
    assert len(response.results) == 0
    assert len(response.errors) == 1
    assert response.errors[0].id == str(media_id)
    assert response.errors[0].error == "Media not ready"

@pytest.mark.asyncio
async def test_batch_sign_immich_copy_mode_success(
    media_service, mock_session, user_id, entry_id, active_immich_integration
):
    """Test signing for Immich Copy-Mode media (downloaded and completed)."""
    media_id = uuid.uuid4()

    # Copy-mode: file_path set, status=COMPLETED
    mock_row = create_mock_media(
        media_id, entry_id, user_id,
        provider="immich",
        asset_id="asset-copy",
        status=UploadStatus.COMPLETED,
        file_path="/path/to/file.jpg",
        thumbnail_path="thumbs/thumb.jpg"
    )

    mock_session.exec.return_value.all.return_value = [mock_row]
    mock_session.exec.return_value.first.return_value = active_immich_integration

    request = MediaBatchSignRequest(items=[
        MediaBatchSignItem(id=str(media_id), variant="original"),
        MediaBatchSignItem(id=str(media_id), variant="thumbnail")
    ])

    with patch("app.services.media_service.signed_url_for_journiv") as mock_sign:
        mock_sign.return_value = "signed-url"
        response = await media_service.batch_sign_media(request, user_id, mock_session)

    # Verify both succeed
    assert len(response.results) == 2
    assert len(response.errors) == 0

@pytest.mark.asyncio
async def test_batch_sign_immich_copy_mode_processing(
    media_service, mock_session, user_id, entry_id, active_immich_integration
):
    """Test signing for Immich Copy-Mode placeholder (still downloading)."""
    media_id = uuid.uuid4()

    # Copy-mode placeholder: status=PROCESSING, file_path=None (usually) or set but processing
    # Even if file_path is set, status=PROCESSING must fail
    mock_row = create_mock_media(
        media_id, entry_id, user_id,
        provider="immich",
        asset_id="asset-copy-pending",
        status=UploadStatus.PROCESSING,
        file_path=None  # Placeholder usually has None
    )

    mock_session.exec.return_value.all.return_value = [mock_row]
    mock_session.exec.return_value.first.return_value = active_immich_integration

    request = MediaBatchSignRequest(items=[
        MediaBatchSignItem(id=str(media_id), variant="original")
    ])

    response = await media_service.batch_sign_media(request, user_id, mock_session)

    assert len(response.results) == 0
    assert len(response.errors) == 1
    assert response.errors[0].error == "Media not ready"

@pytest.mark.asyncio
async def test_batch_sign_immich_copy_mode_thumbnail_missing(
    media_service, mock_session, user_id, entry_id, active_immich_integration
):
    """Test signing for Immich Copy-Mode where thumbnail is missing."""
    media_id = uuid.uuid4()

    # Copy-mode: file_path set (local), but thumbnail_path is None
    mock_row = create_mock_media(
        media_id, entry_id, user_id,
        provider="immich",
        asset_id="asset-copy-no-thumb",
        status=UploadStatus.COMPLETED,
        file_path="/path/to/file.jpg",
        thumbnail_path=None
    )

    mock_session.exec.return_value.all.return_value = [mock_row]
    mock_session.exec.return_value.first.return_value = active_immich_integration

    # Request thumbnail
    request = MediaBatchSignRequest(items=[
        MediaBatchSignItem(id=str(media_id), variant="thumbnail")
    ])

    response = await media_service.batch_sign_media(request, user_id, mock_session)

    # Should fail because local thumbnail is missing
    assert len(response.results) == 0
    assert len(response.errors) == 1
    assert response.errors[0].error == "Thumbnail not available"

@pytest.mark.asyncio
async def test_batch_sign_immich_link_only_thumbnail_proxy(
    media_service, mock_session, user_id, entry_id, active_immich_integration
):
    """Test signing for Immich Link-Only thumbnail (should succeed without local thumb)."""
    media_id = uuid.uuid4()

    # Link-only: file_path=None, thumbnail_path=None
    mock_row = create_mock_media(
        media_id, entry_id, user_id,
        provider="immich",
        asset_id="asset-link-only",
        status=UploadStatus.COMPLETED,
        file_path=None,
        thumbnail_path=None
    )

    mock_session.exec.return_value.all.return_value = [mock_row]
    mock_session.exec.return_value.first.return_value = active_immich_integration

    request = MediaBatchSignRequest(items=[
        MediaBatchSignItem(id=str(media_id), variant="thumbnail")
    ])

    with patch("app.services.media_service.signed_url_for_journiv") as mock_sign:
        mock_sign.return_value = "signed-url"
        response = await media_service.batch_sign_media(request, user_id, mock_session)

    # Should succeed - will be proxied
    assert len(response.results) == 1
    assert len(response.errors) == 0
