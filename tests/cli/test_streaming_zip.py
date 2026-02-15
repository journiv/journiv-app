"""
Unit tests for streaming ZIP extraction.

Tests the memory-efficient stream_extract() method.
"""
import pytest
import zipfile
import tempfile
import unittest.mock
from pathlib import Path

from app.utils.import_export.zip_handler import ZipHandler


class TestStreamingZip:
    """Test streaming ZIP extraction."""

    @pytest.fixture
    def temp_dir(self, monkeypatch):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            # Patch settings to allow extraction to this temp dir
            monkeypatch.setattr("app.core.config.settings.import_temp_dir", str(path))
            yield path

    @pytest.fixture
    def sample_zip(self, temp_dir):
        """Create a sample ZIP file for testing."""
        zip_path = temp_dir / "test.zip"

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Add data.json
            zipf.writestr("data.json", '{"journals": [], "version": "1.0"}')

            # Add media files
            zipf.writestr("media/entry1/photo1.jpg", b"fake image data")
            zipf.writestr("media/entry1/photo2.jpg", b"another fake image")
            zipf.writestr("media/entry2/video.mp4", b"fake video data")

        return zip_path

    def test_stream_extract_basic(self, sample_zip, temp_dir):
        """Test basic streaming extraction."""
        extract_to = temp_dir / "extracted"

        result = ZipHandler.stream_extract(
            zip_path=sample_zip,
            extract_to=extract_to,
            max_size_mb=10,
            validate_media=False,  # Disable for basic test
        )

        # Verify result structure
        assert "data_file" in result
        assert "media_dir" in result
        assert "total_size" in result
        assert "file_count" in result

        # Verify data file exists
        assert result["data_file"].exists()
        assert result["data_file"].name == "data.json"

        # Verify file count
        assert result["file_count"] == 4  # data.json + 3 media files

    def test_stream_extract_with_progress(self, sample_zip, temp_dir):
        """Test streaming extraction with progress callback."""
        extract_to = temp_dir / "extracted"
        progress_calls = []

        def track_progress(current, total):
            progress_calls.append((current, total))

        ZipHandler.stream_extract(
            zip_path=sample_zip,
            extract_to=extract_to,
            max_size_mb=10,
            validate_media=False,
            progress_callback=track_progress,
        )

        # Verify progress callback was called
        assert len(progress_calls) == 4  # Once per file
        assert progress_calls[-1] == (4, 4)  # Last call should be (total, total)

    def test_stream_extract_zero_copy_media(self, sample_zip, temp_dir):
        """Test zero-copy media extraction to custom destination."""
        extract_to = temp_dir / "extracted"
        media_dest = temp_dir / "media_storage" / "user123"

        ZipHandler.stream_extract(
            zip_path=sample_zip,
            extract_to=extract_to,
            media_dest=media_dest,
            max_size_mb=10,
            validate_media=False,
        )

        # Verify data.json is in extract_to
        assert (extract_to / "data.json").exists()

        # Verify media files are in media_dest (zero-copy)
        assert (media_dest / "entry1" / "photo1.jpg").exists()
        assert (media_dest / "entry1" / "photo2.jpg").exists()
        assert (media_dest / "entry2" / "video.mp4").exists()

        # Verify media files are NOT in extract_to
        assert not (extract_to / "media").exists()

    def test_stream_extract_size_limit(self, temp_dir):
        """Test size limit enforcement."""
        # Create a ZIP that exceeds limit
        zip_path = temp_dir / "large.zip"

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.writestr("data.json", '{"journals": []}')
            # Add large fake file
            large_data = b"x" * (10 * 1024 * 1024)  # 10MB
            zipf.writestr("media/large.jpg", large_data)

        extract_to = temp_dir / "extracted"

        # Should raise ValueError for exceeding size
        with pytest.raises(ValueError, match="ZIP too large"):
            ZipHandler.stream_extract(
                zip_path=zip_path,
                extract_to=extract_to,
                max_size_mb=5,  # Limit to 5MB
                validate_media=False,
            )

    def test_stream_extract_path_traversal(self, temp_dir):
        """Test path traversal protection."""
        zip_path = temp_dir / "malicious.zip"

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.writestr("data.json", '{"journals": []}')
            # Try to write outside extraction directory
            zipf.writestr("../../../etc/passwd", "malicious content")

        extract_to = temp_dir / "extracted"

        # Should raise ValueError for unsafe path
        with pytest.raises(ValueError, match="unsafe path"):
            ZipHandler.stream_extract(
                zip_path=zip_path,
                extract_to=extract_to,
                max_size_mb=10,
                validate_media=False,
            )

    def test_stream_extract_corrupted_zip(self, temp_dir):
        """Test handling of corrupted ZIP file."""
        zip_path = temp_dir / "corrupted.zip"

        # Create corrupted ZIP
        with open(zip_path, 'wb') as f:
            f.write(b"PK\x03\x04" + b"corrupted data")

        extract_to = temp_dir / "extracted"

        # Should raise ValueError or IOError
        with pytest.raises((ValueError, IOError)):
            ZipHandler.stream_extract(
                zip_path=zip_path,
                extract_to=extract_to,
                max_size_mb=10,
                validate_media=False,
            )

    def test_stream_extract_missing_data_file(self, temp_dir):
        """Test handling of ZIP without data.json."""
        zip_path = temp_dir / "no_data.zip"

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.writestr("media/photo.jpg", b"image data")

        extract_to = temp_dir / "extracted"

        # Should raise ValueError or IOError for missing data.json
        with pytest.raises((ValueError, IOError), match="Extracted data file not found"):
            ZipHandler.stream_extract(
                zip_path=zip_path,
                extract_to=extract_to,
                max_size_mb=10,
                validate_media=False,
            )

    def test_stream_extract_symlink(self, temp_dir):
        """Test symlink detection."""
        zip_path = temp_dir / "symlink.zip"

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.writestr("data.json", '{"journals": []}')
            # Create a symlink entry
            info = zipfile.ZipInfo("link_to_passwd")
            info.create_system = 3  # Unix
            info.external_attr = 0o120000 << 16  # Symlink
            zipf.writestr(info, "/etc/passwd")

        extract_to = temp_dir / "extracted"

        with pytest.raises(ValueError, match="ZIP contains symlink"):
            ZipHandler.stream_extract(
                zip_path=zip_path,
                extract_to=extract_to,
                max_size_mb=10,
                validate_media=False,
            )

    def test_stream_extract_null_byte_filename(self, temp_dir):
        """Test null byte in filename detection (using mock since zipfile sanitizes on read)."""
        zip_path = temp_dir / "null_byte.zip"

        # Create a valid zip first
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.writestr("data.json", '{"journals": []}')

        extract_to = temp_dir / "extracted"

        # Mock zipfile.ZipFile to return an entry with null byte
        with unittest.mock.patch('zipfile.ZipFile') as MockZipFile:
            mock_zip = MockZipFile.return_value.__enter__.return_value
            mock_zip.testzip.return_value = None

            # Create info with null byte (assign directly to bypass sanitization)
            bad_info = zipfile.ZipInfo("malicious_file.txt")
            bad_info.filename = "malicious\x00file.txt"
            bad_info.file_size = 10

            # Mock infolist to return our bad info
            mock_zip.infolist.return_value = [bad_info]

            with pytest.raises(ValueError, match="ZIP contains invalid filename"):
                ZipHandler.stream_extract(
                    zip_path=zip_path,
                    extract_to=extract_to,
                    max_size_mb=10,
                    validate_media=False,
                )
