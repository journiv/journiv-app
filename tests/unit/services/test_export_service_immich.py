from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.models.moment import MomentMedia
from app.models.enums import MediaType, UploadStatus
from app.services.export_service import ExportService


def test_convert_media_to_dto_immich_asset_no_filepath():
    """
    Test that _convert_media_to_dto handles Immich assets linked externally.
    These assets have file_path=None.
    """
    # Mock DB session
    db = MagicMock()
    service = ExportService(db)

    # Mock settings.media_root
    with patch('app.services.export_service.settings') as mock_settings:
        mock_settings.media_root = "/tmp/media"

        # Create Mock Media object simulating an Immich asset
        media_mock = MagicMock(spec=MomentMedia)
        media_mock.id = uuid4()
        media_mock.moment_id = uuid4()
        # file_path is None for Immich assets in link mode
        media_mock.file_path = None
        media_mock.original_filename = "immich_photo.jpg"
        media_mock.media_type = MediaType.IMAGE
        media_mock.file_size = 5000
        media_mock.mime_type = "image/jpeg"
        media_mock.checksum = "abc123hash"
        media_mock.width = 1920
        media_mock.height = 1080
        media_mock.duration = None
        media_mock.alt_text = "Vacation photo"
        media_mock.file_metadata = '{"exif": "data"}'
        media_mock.thumbnail_path = "thumbs/immich_photo.jpg"
        media_mock.upload_status = UploadStatus.COMPLETED
        media_mock.created_at = datetime.now(timezone.utc)

        media_mock.updated_at = datetime.now(timezone.utc)

        # Explicitly set external fields to None to avoid MagicMock objects being passed to Pydantic
        media_mock.external_provider = None
        media_mock.external_asset_id = None
        media_mock.external_url = None
        media_mock.external_created_at = None
        media_mock.external_metadata = None

        # Act
        # This call would previously crash with TypeError
        dto = service._convert_media_to_dto(media_mock)

        # Assert
        assert dto.filename == "immich_photo.jpg"
        assert dto.file_path is None
        assert dto.media_type == "image"
        # Verify external fields are populated
        assert dto.external_provider is None # Mock didn't set it, but field should exist
        assert dto.external_asset_id is None

        # Verify it wasn't added to export map (since it shouldn't have a local path)
        assert len(service._media_export_map) == 0

def test_convert_media_to_dto_immich_asset_fallback_filename():
    """
    Test fallback filename when original_filename is missing and file_path is None.
    """
    db = MagicMock()
    service = ExportService(db)

    with patch('app.services.export_service.settings') as mock_settings:
        mock_settings.media_root = "/tmp/media"

        media_mock = MagicMock(spec=MomentMedia)
        media_mock.id = uuid4()
        media_mock.moment_id = uuid4()
        media_mock.file_path = None
        media_mock.original_filename = None
        media_mock.media_type = MediaType.IMAGE
        media_mock.file_size = None # Can be None in DB
        media_mock.mime_type = "image/jpeg"
        media_mock.upload_status = UploadStatus.COMPLETED
        media_mock.created_at = datetime.now(timezone.utc)
        media_mock.updated_at = datetime.now(timezone.utc)

        # Defaults for other fields to avoid attr errors in DTO init
        media_mock.checksum = None
        media_mock.width = None
        media_mock.height = None
        media_mock.duration = None
        media_mock.alt_text = None
        media_mock.file_metadata = None
        media_mock.thumbnail_path = None

        # Explicitly set external fields to None
        media_mock.external_provider = None
        media_mock.external_asset_id = None
        media_mock.external_url = None
        media_mock.external_created_at = None
        media_mock.external_metadata = None

        dto = service._convert_media_to_dto(media_mock)

        assert dto.filename == f"media_{media_mock.id}"
        assert dto.file_size == 0

        # Verify external assets weren't added to export map
        assert media_mock.id not in service._media_export_map
