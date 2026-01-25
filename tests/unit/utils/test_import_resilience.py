import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from app.utils.import_export.zip_handler import ZipHandler
from app.utils.import_export.media_handler import MediaHandler
from app.core.config import settings

def test_media_handler_validate_media_returns_4_values():
    """Test that MediaHandler.validate_media returns (is_valid, mime_type, category, error_msg)."""
    # Create a dummy file portably
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
        tf.write(b"dummy data")
        test_file = Path(tf.name)

    try:
        # Mock detect_mime to return a specific type
        with patch.object(MediaHandler, 'detect_mime', return_value="image/jpeg"):
            res = MediaHandler.validate_media(
                test_file,
                max_size_mb=10,
                allowed_types=["image/jpeg"],
                allowed_extensions=[".jpg"]
            )

            assert len(res) == 4
            is_valid, mime_type, category, error_msg = res
            assert is_valid is True
            assert mime_type == "image/jpeg"
            assert category == "none"
            assert error_msg == "File is valid"
    finally:
        if test_file.exists():
            test_file.unlink()

def test_media_handler_quicktime_support():
    """Test that video/quicktime and .mov are correctly handled."""
    assert ".mov" in MediaHandler.MIME_TYPE_MAP
    assert MediaHandler.MIME_TYPE_MAP[".mov"] == "video/quicktime"
    assert ".mov" in MediaHandler.VIDEO_EXTENSIONS

@patch("zipfile.ZipFile")
def test_zip_handler_stream_extract_warning_categorization(mock_zipfile):
    """Test that stream_extract categorizes validation warnings."""
    # Setup mock zip info
    mock_info = MagicMock()
    mock_info.filename = "media/too_large.jpg"
    mock_info.is_dir.return_value = False
    mock_info.file_size = 1000

    # Mock ZipFile behavior
    instance = mock_zipfile.return_value.__enter__.return_value
    instance.testzip.return_value = None
    instance.infolist.return_value = [mock_info]

    # Mock MediaHandler.validate_media to fail with size error
    with patch("app.utils.import_export.media_handler.MediaHandler.validate_media") as mock_val:
        mock_val.return_value = (False, "image/jpeg", "size", "File size exceeds maximum limit")

        # Mock FS operations to prevent actual I/O
        with patch("pathlib.Path.mkdir", MagicMock()), \
             patch("app.utils.import_export.zip_handler.open", MagicMock()), \
             patch("shutil.copyfileobj", MagicMock()), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.unlink") as mock_unlink, \
             patch("pathlib.Path.glob", return_value=[Path("/tmp/data.json")]):

            result = ZipHandler.stream_extract(
                zip_path=Path("dummy.zip"),
                extract_to=Path("/tmp/extract_to"),
                media_dest=Path("/tmp/media_dest"),
                max_size_mb=1,
                validate_media=True
            )

            assert "warnings" in result
            assert len(result["warnings"]) == 1
            assert "warning_categories" in result
            assert result["warning_categories"]["Skipped due to size"] == 1

            # Verify the invalid file was unlinked
            assert mock_unlink.called

@patch("zipfile.ZipFile")
def test_zip_handler_stream_extract_direct_to_media_dest(mock_zipfile):
    """Test that media files are extracted directly to media_dest when provided."""
    # Setup mock zip info for a media file
    mock_info = MagicMock()
    mock_info.filename = "media/photo.jpg"
    mock_info.is_dir.return_value = False
    mock_info.file_size = 100

    # Mock ZipFile behavior
    instance = mock_zipfile.return_value.__enter__.return_value
    instance.testzip.return_value = None
    instance.infolist.return_value = [mock_info]

    # Mock MediaHandler.validate_media to succeed
    with patch("app.utils.import_export.media_handler.MediaHandler.validate_media") as mock_val:
        mock_val.return_value = (True, "image/jpeg", "none", "Valid")

        # Track the path passed to open()
        from unittest.mock import mock_open
        m_open = mock_open()

        extract_to = Path("/tmp/extract_to")
        media_dest = Path("/tmp/media_dest")

        with patch("pathlib.Path.mkdir", MagicMock()), \
             patch("app.utils.import_export.zip_handler.open", m_open), \
             patch("shutil.copyfileobj", MagicMock()), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.glob", return_value=[Path("/tmp/data.json")]):

            ZipHandler.stream_extract(
                zip_path=Path("dummy.zip"),
                extract_to=extract_to,
                media_dest=media_dest,
                max_size_mb=1,
                validate_media=True
            )

            # Verify open was called with a path inside media_dest, not extract_to
            target_path = m_open.call_args[0][0]
            assert str(media_dest) in str(target_path)
            assert str(extract_to) not in str(target_path)
