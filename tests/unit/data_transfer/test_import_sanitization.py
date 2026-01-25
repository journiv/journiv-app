from datetime import datetime, timezone
from pathlib import Path
import uuid
from unittest.mock import MagicMock
from app.data_transfer.dayone.mappers import DayOneToJournivMapper
from app.services.import_service import ImportService
from app.schemas.dto import ImportResultSummary, MediaDTO
from app.models.enums import MediaType, UploadStatus

def test_dayone_mapper_sanitizes_zero_dimensions(tmp_path):
    """Test that DayOneToJournivMapper converts 0 width/height to None."""
    photo_file = tmp_path / "dummy_photo.jpg"
    photo_file.write_bytes(b"dummy_data")

    dto = DayOneToJournivMapper._map_media_common(
        media_path=photo_file,
        identifier="PHOTO-1",
        entry_external_id="ENTRY-1",
        media_base_dir=tmp_path,
        media_type="image",
        mime_type="image/jpeg",
        width=0,
        height=0,
        duration=None,
        date=datetime.now(timezone.utc),
        file_metadata={}
    )

    assert dto.width is None
    assert dto.height is None

def test_import_service_sanitizes_zero_dimensions():
    """Test that ImportService._create_media_record converts 0 width/height to None."""
    # Mock ImportService and call helper method
    service = ImportService(db=None)

    now = datetime.now(timezone.utc)
    media_dto = MediaDTO(
        filename="test.jpg",
        file_path="user/images/test.jpg",
        media_type="image",
        file_size=1024,
        mime_type="image/jpeg",
        width=0,
        height=0,
        created_at=now,
        updated_at=now
    )

    # Mocking behaviors to avoid DB calls
    service._parse_media_type = MagicMock(return_value=MediaType.IMAGE)
    service._parse_upload_status = MagicMock(return_value=UploadStatus.COMPLETED)

    # Use the correct method name: _create_media_record
    record = service._create_media_record(
        entry_id=uuid.uuid4(),
        file_path="user/images/test.jpg",
        media_dto=media_dto,
        checksum="dummy_checksum",
        file_size=1024
    )

    assert record.width is None
    assert record.height is None

def test_import_service_add_warning_categorization():
    """Test that _add_warning correctly categorizes warnings."""
    summary = ImportResultSummary()
    ImportService._add_warning(summary, "Test message", "Test Category")

    assert "Test message" in summary.warnings
    assert summary.warning_categories["Test Category"] == 1

    ImportService._add_warning(summary, "Another message", "Test Category")
    assert summary.warning_categories["Test Category"] == 2
