from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest
from fastapi import HTTPException, UploadFile

from app.utils.import_export.upload_manager import UploadManager


# Mock settings
@pytest.fixture
def mock_settings():
    with patch("app.utils.import_export.upload_manager.settings") as mock:
        mock.import_temp_dir = "/tmp/journiv-test/imports"
        mock.import_export_max_file_size_mb = 10
        yield mock

@pytest.fixture
def mock_upload_file():
    file_mock = MagicMock(spec=UploadFile)
    file_mock.filename = "test_archive.zip"
    file_mock.file = MagicMock()
    # Setup async read mock for fallback path
    file_mock.read = AsyncMock()
    return file_mock

@pytest.mark.asyncio
async def test_process_upload_success(mock_settings, mock_upload_file):
    """Test successful upload processing with standard zip file."""
    # Setup
    mock_upload_file.file.read.side_effect = [b"chunk1", b"chunk2", b""] # Simulate chunks

    with patch("builtins.open", mock_open()) as mock_file_open:
        with patch.object(Path, "mkdir") as mock_mkdir:
            with patch("app.utils.import_export.upload_manager.ZipHandler") as mock_zip_handler_cls:
                # Mock zip validation to pass
                mock_zip_handler = mock_zip_handler_cls.return_value
                mock_zip_handler.validate_zip_structure.return_value = {"valid": True, "errors": []}

                # Excecute
                result_path = await UploadManager.process_upload(mock_upload_file, "journiv")

                # Verify
                assert result_path is not None
                assert "test_archive" in str(result_path)
                mock_mkdir.assert_called()
                # Verify chunks were written
                handle = mock_file_open()
                handle.write.assert_any_call(b"chunk1")
                handle.write.assert_any_call(b"chunk2")

@pytest.mark.asyncio
async def test_process_upload_invalid_extension(mock_upload_file):
    """Test that non-zip files are rejected."""
    mock_upload_file.filename = "image.png"

    with pytest.raises(HTTPException) as exc:
        await UploadManager.process_upload(mock_upload_file, "journiv")

    assert exc.value.status_code == 400
    assert "must be a ZIP archive" in exc.value.detail

@pytest.mark.asyncio
async def test_process_upload_too_large(mock_settings, mock_upload_file):
    """Test that files exceeding size limit are caught during streaming."""
    mock_settings.import_export_max_file_size_mb = 1 # 1 MB limit

    # Create a chunk larger than 1MB
    large_chunk = b"x" * (1024 * 1024 + 100)
    mock_upload_file.file.read.side_effect = [large_chunk]

    with patch("builtins.open", mock_open()):
        with patch.object(Path, "mkdir"):
            with patch("pathlib.Path.unlink") as mock_unlink:
                 with pytest.raises(HTTPException) as exc:
                     await UploadManager.process_upload(mock_upload_file, "journiv")

                 assert exc.value.status_code == 413
                 assert "File too large" in exc.value.detail
                 # Verify partial file is cleaned up
                 mock_unlink.assert_called()

@pytest.mark.asyncio
async def test_process_upload_invalid_zip_structure(mock_settings, mock_upload_file):
    """Test that invalid zip files are rejected after upload."""
    mock_upload_file.file.read.side_effect = [b"some valid bytes", b""]

    with patch("builtins.open", mock_open()):
        with patch.object(Path, "mkdir"):
            with patch("app.utils.import_export.upload_manager.ZipHandler") as mock_zip_handler_cls:
                mock_zip_handler = mock_zip_handler_cls.return_value
                # Mock validation failure
                mock_zip_handler.validate_zip_structure.return_value = {
                    "valid": False,
                    "errors": ["Missing data.json"]
                }

                with patch("pathlib.Path.unlink") as mock_unlink:
                    with pytest.raises(HTTPException) as exc:
                        await UploadManager.process_upload(mock_upload_file, "journiv")

                    assert exc.value.status_code == 400
                    assert "Invalid ZIP file" in exc.value.detail
                    mock_unlink.assert_called()
