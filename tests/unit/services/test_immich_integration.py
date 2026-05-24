from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.models.enums import MediaType, UploadStatus
from app.models.moment import MomentMedia
from app.models.person import Person
from app.models.person_external_identity import PersonExternalIdentity
from app.schemas.dto import MomentMediaDTO
from app.services.export_service import ExportService
from app.services.immich_face_service import ImmichFaceService
from app.services.import_service import ImportService


def test_export_includes_external_fields():
    """Verify that export service populates external fields in MomentMediaDTO."""
    db = MagicMock()
    service = ExportService(db)

    with patch('app.services.export_service.settings') as mock_settings:
        mock_settings.media_root = "/tmp/media"

        # Create media with external fields
        media = MagicMock(spec=MomentMedia)
        media.id = uuid4()
        media.moment_id = uuid4()
        media.file_path = None
        media.original_filename = "photo.jpg"
        media.media_type = MediaType.IMAGE
        media.file_size = 1234
        media.mime_type = "image/jpeg"
        media.upload_status = UploadStatus.COMPLETED
        media.created_at = datetime.now(timezone.utc)
        media.updated_at = datetime.now(timezone.utc)

        # External fields
        media.external_provider = "immich"
        media.external_asset_id = "asset-123"
        media.external_url = "https://immich.example.com/asset-123"
        media.external_created_at = datetime(2023, 1, 1, tzinfo=timezone.utc)
        media.external_metadata = {"exif": "data"}

        # Default others
        media.checksum = None
        media.width = 100
        media.height = 100
        media.duration = None
        media.alt_text = None
        media.thumbnail_path = None
        media.file_metadata = None

        dto = service._convert_media_to_dto(media)

        assert dto.external_provider == "immich"
        assert dto.external_asset_id == "asset-123"
        assert dto.external_url == "https://immich.example.com/asset-123"
        assert dto.external_created_at == datetime(2023, 1, 1, tzinfo=timezone.utc)
        assert dto.external_metadata == {"exif": "data"}


def test_immich_face_response_does_not_suggest_archived_person():
    """Archived mapped people should not be auto-suggested from Immich faces."""
    service = ImmichFaceService(MagicMock())
    person_id = uuid4()
    user_id = uuid4()

    person = MagicMock(spec=Person)
    person.id = person_id
    person.name = "Archived Person"
    person.nickname = None
    person.profile_image_path = None
    person.archived_at = datetime.now(timezone.utc)

    identity = MagicMock(spec=PersonExternalIdentity)
    identity.sync_enabled = True

    face = MagicMock()
    face.person_id = person_id
    face.external_person_id = "immich-person-1"
    face.user_id = user_id
    face.external_face_id = "face-1"
    face.external_asset_id = "asset-1"
    face.is_hidden = False
    face.bounding_box_x1 = None
    face.bounding_box_y1 = None
    face.bounding_box_x2 = None
    face.bounding_box_y2 = None
    face.image_width = None
    face.image_height = None
    face.source_type = None
    face.last_synced_at = datetime.now(timezone.utc)

    response = service._face_response(
        face,
        people_by_id={person_id: person},
        identities_by_external_id={"immich-person-1": identity},
    )

    assert response.person is not None
    assert response.suggested is False

def test_import_handles_external_media_link_only():
    """Verify that import service handles media with external_provider but no file_path."""
    db = MagicMock()
    service = ImportService(db)

    # Setup DTO with external fields and NO file_path
    media_dto = MomentMediaDTO(
        filename="photo.jpg",
        media_type="image",
        file_size=1000,
        mime_type="image/jpeg",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        external_provider="immich",
        external_asset_id="asset-123",
        external_url="https://immich.example.com/assets/asset-123",
        external_metadata={"foo": "bar"}
    )

    moment_id = uuid4()
    user_id = uuid4()

    # Simulate no existing media found (for deduplication check)
    db.query.return_value.filter.return_value.first.return_value = None

    # Mock _create_media_record to return a media object
    with patch.object(service, '_create_media_record') as mock_create:
        mock_media = MagicMock(spec=MomentMedia)
        mock_media.id = uuid4()
        mock_create.return_value = mock_media
        result = service._import_media(
            moment_id=moment_id,
            user_id=user_id,
            media_dto=media_dto,
            media_dir=Path("/tmp/media"), # Should be ignored for external
            existing_checksums=set(),
            summary=MagicMock()
        )

        assert result["imported"] is True
        assert result["media_id"] == str(mock_media.id)

        # Verify _create_media_record was called with correct args
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs['file_path'] is None
        assert call_kwargs['media_dto'].external_provider == "immich"

def test_create_media_record_populates_external_fields():
    """Verify that _create_media_record populates MomentMedia with external fields."""
    db = MagicMock()
    service = ImportService(db)

    media_dto = MomentMediaDTO(
        filename="photo.jpg",
        media_type="image",
        file_size=1000,
        mime_type="image/jpeg",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        external_provider="immich",
        external_asset_id="asset-123",
        external_url="https://immich.example.com/assets/asset-123",
        external_created_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
        external_metadata={"foo": "bar"}
    )

    media = service._create_media_record(
        moment_id=uuid4(),
        file_path=None,
        media_dto=media_dto,
        checksum="hash123",
        file_size=1000
    )

    assert media.external_provider == "immich"
    assert media.external_asset_id == "asset-123"
    assert media.external_url == "https://immich.example.com/assets/asset-123"
    assert media.external_created_at == datetime(2023, 1, 1, tzinfo=timezone.utc)
    assert media.external_metadata == {"foo": "bar"}

def test_import_handles_external_media_with_no_media_dir():
    """Verify that import service handles external media when media_dir is None."""
    db = MagicMock()
    service = ImportService(db)

    # Setup DTO with external fields and NO file_path
    media_dto = MomentMediaDTO(
        filename="photo.jpg",
        media_type="image",
        file_size=1000,
        mime_type="image/jpeg",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        external_provider="immich",
        external_asset_id="asset-123",
        external_url="https://immich.example.com/assets/asset-123",
        external_metadata={"foo": "bar"}
    )

    moment_id = uuid4()
    user_id = uuid4()

    # Simulate no existing media found (for deduplication check)
    db.query.return_value.filter.return_value.first.return_value = None

    # Mock _create_media_record to return a media object
    with patch.object(service, '_create_media_record') as mock_create:
        mock_media = MagicMock(spec=MomentMedia)
        mock_media.id = uuid4()
        mock_create.return_value = mock_media

        # Pass media_dir=None explicitly
        result = service._import_media(
            moment_id=moment_id,
            user_id=user_id,
            media_dto=media_dto,
            media_dir=None, # Typical for imports with only external media
            existing_checksums=set(),
            summary=MagicMock()
        )

        assert result["imported"] is True
        assert result["media_id"] == str(mock_media.id)

        # Verify _create_media_record was called with correct args
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs['file_path'] is None
        assert call_kwargs['media_dto'].external_provider == "immich"


def test_import_allows_duplicate_external_media():
    """Verify that import ALLOWS duplicate external media (does not deduplicate)."""
    db = MagicMock()
    service = ImportService(db)

    media_dto = MomentMediaDTO(
        filename="photo.jpg",
        media_type="image",
        file_size=1000,
        mime_type="image/jpeg",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        external_provider="immich",
        external_asset_id="asset-123", # Same asset ID
        external_url="https://immich.example.com/assets/asset-123"
    )

    moment_id = uuid4()
    user_id = uuid4()

    # Simulate existing media usually would be found if we queried, but we don't query.
    # We can mock the query to ensure it's NOT CALLED or just verify creation happens.

    # Mock _create_media_record - SHOULD be called now
    with patch.object(service, '_create_media_record') as mock_create:
        mock_media = MagicMock(spec=MomentMedia)
        mock_media.id = uuid4()
        mock_create.return_value = mock_media

        result = service._import_media(
            moment_id=moment_id,
            user_id=user_id,
            media_dto=media_dto,
            media_dir=None,
            existing_checksums=set(),
            summary=MagicMock()
        )

        assert result["imported"] is True
        assert result["deduplicated"] is False
        assert result["media_id"] == str(mock_media.id)

        # Verify creation WAS called
        mock_create.assert_called_once()
