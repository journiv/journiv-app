"""
Tests for HEIC/HEIF display version support in MediaService.

Covers:
- _needs_display_version detection
- _build_display_path naming convention
- _generate_heic_display_version transcoding (requires pillow-heif)
- process_uploaded_file skips regeneration when display_path exists
- get_media_file_for_serving transparently serves display version
- delete_media_by_id cleans up display version file
"""
import shutil
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlmodel import Session, create_engine

from app.models.base import BaseModel
from app.models.entry import Entry
from app.models.moment import MomentMedia
from app.models.enums import JournalColor, MediaType, UploadStatus
from app.models.journal import Journal
from app.models.moment import Moment
from app.models.user import User
from app.services import media_service as media_service_module
from app.services.media_service import MediaService
from app.services.media_storage_service import MediaStorageService
from app.utils.import_export.media_handler import MediaHandler

HEIC_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "heic_sample.heic"

# ─── helpers & fixtures ──────────────────────────────────────────────

@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


@pytest.fixture
def test_user(test_db: Session) -> User:
    user = User(
        email=f"heic_{uuid.uuid4().hex[:8]}@example.com",
        password="hashed_password",
        name="HEIC Test User",
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def test_entry(test_db: Session, test_user: User) -> Entry:
    journal = Journal(
        user_id=test_user.id,
        title="Test Journal",
        color=JournalColor.BLUE,
    )
    test_db.add(journal)
    test_db.commit()
    test_db.refresh(journal)

    moment = Moment(
        user_id=test_user.id,
        logged_timezone="UTC",
    )
    test_db.add(moment)
    test_db.commit()
    test_db.refresh(moment)

    entry = Entry(
        journal_id=journal.id,
        moment_id=moment.id,
        user_id=test_user.id,
        title="HEIC Entry",
        content_delta={"ops": [{"insert": "test\n"}]},
        content_plain_text="test",
        word_count=1,
    )
    test_db.add(entry)
    test_db.commit()
    test_db.refresh(entry)
    return entry


def _build_service(tmp_path: Path, session: Session) -> MediaService:
    media_root = tmp_path / "media"
    media_root.mkdir()
    media_service_module.settings.media_root = str(media_root)
    service = MediaService(session=session)
    service.media_root = media_root
    service.media_storage_service = MediaStorageService(media_root, session)
    return service


# ─── _needs_display_version ──────────────────────────────────────────

class TestNeedsDisplayVersion:
    def test_heic_extension_returns_true(self):
        assert MediaService._needs_display_version(Path("photo.heic"), "") is True

    def test_heif_extension_returns_true(self):
        assert MediaService._needs_display_version(Path("photo.heif"), "") is True

    def test_heic_mime_type_returns_true(self):
        assert MediaService._needs_display_version(Path("photo.bin"), "image/heic") is True

    def test_heif_mime_type_returns_true(self):
        assert MediaService._needs_display_version(Path("photo.bin"), "image/heif") is True

    def test_heic_sequence_mime_returns_true(self):
        assert MediaService._needs_display_version(Path("x"), "image/heic-sequence") is True

    def test_heif_sequence_mime_returns_true(self):
        assert MediaService._needs_display_version(Path("x"), "image/heif-sequence") is True

    def test_jpeg_returns_false(self):
        assert MediaService._needs_display_version(Path("photo.jpg"), "image/jpeg") is False

    def test_png_returns_false(self):
        assert MediaService._needs_display_version(Path("img.png"), "image/png") is False

    def test_case_insensitive_extension(self):
        assert MediaService._needs_display_version(Path("PHOTO.HEIC"), "") is True


# ─── _build_display_path ─────────────────────────────────────────────

class TestBuildDisplayPath:
    def test_basic_heic(self):
        result = MediaService._build_display_path(Path("/data/media/abc123.heic"))
        assert result == Path("/data/media/abc123_display.webp")

    def test_heif_extension(self):
        result = MediaService._build_display_path(Path("/data/media/photo.heif"))
        assert result == Path("/data/media/photo_display.webp")

    def test_preserves_parent_directory(self):
        result = MediaService._build_display_path(Path("/data/user1/images/img.heic"))
        assert result.parent == Path("/data/user1/images")

    def test_complex_stem(self):
        result = MediaService._build_display_path(Path("/data/a1b2c3d4_checksum.heic"))
        assert result.name == "a1b2c3d4_checksum_display.webp"


# ─── _generate_heic_display_version ──────────────────────────────────

try:
    from pillow_heif import register_heif_opener
    _pillow_heif_installed = True
except ImportError:
    _pillow_heif_installed = False


@pytest.mark.skipif(
    not _pillow_heif_installed or not HEIC_FIXTURE.exists(),
    reason="pillow-heif not installed or HEIC fixture missing",
)
class TestGenerateHeicDisplayVersion:
    def test_generates_webp_from_heic(self, tmp_path, test_db):
        """End-to-end: real HEIC fixture → WebP display version."""
        service = _build_service(tmp_path, test_db)

        # Copy fixture into tmp media dir
        heic_path = tmp_path / "media" / "test.heic"
        shutil.copy(HEIC_FIXTURE, heic_path)

        result = service._generate_heic_display_version(heic_path)

        assert result is not None
        assert result.exists()
        assert result.suffix == ".webp"
        assert result.name == "test_display.webp"
        assert result.stat().st_size > 0

    def test_atomic_write_no_partial_files(self, tmp_path, test_db):
        """On success, no .tmp.webp files should remain."""
        service = _build_service(tmp_path, test_db)
        heic_path = tmp_path / "media" / "atomic.heic"
        shutil.copy(HEIC_FIXTURE, heic_path)

        service._generate_heic_display_version(heic_path)

        tmp_files = list(tmp_path.rglob("*.tmp.webp"))
        assert tmp_files == []

    def test_returns_none_for_corrupt_file(self, tmp_path, test_db):
        """Corrupt file should return None and clean up."""
        service = _build_service(tmp_path, test_db)
        corrupt_path = tmp_path / "media" / "corrupt.heic"
        corrupt_path.write_bytes(b"this is not a heic file")

        result = service._generate_heic_display_version(corrupt_path)

        assert result is None
        # No leftover display or tmp files
        assert not (tmp_path / "media" / "corrupt_display.webp").exists()
        assert list(tmp_path.rglob("*.tmp.webp")) == []


class TestGenerateHeicWithoutSupport:
    def test_returns_none_when_heif_not_available(self, tmp_path, test_db):
        """When _HEIF_SUPPORT is False, should return None gracefully."""
        service = _build_service(tmp_path, test_db)
        heic_path = tmp_path / "media" / "test.heic"
        heic_path.write_bytes(b"fake")

        with patch("app.services.media_service._HEIF_SUPPORT", False):
            result = service._generate_heic_display_version(heic_path)

        assert result is None


# ─── process_uploaded_file: skip when display_path exists ────────────

class TestProcessUploadedFileHeicSkip:
    def test_skips_display_generation_when_already_exists(
        self, tmp_path, test_db, test_user, test_entry
    ):
        """If display_path is already set and the file exists, don't regenerate."""
        service = _build_service(tmp_path, test_db)
        media_root = tmp_path / "media"

        # Create a fake HEIC file and a pre-existing display version
        user_dir = media_root / str(test_user.id) / "images"
        user_dir.mkdir(parents=True)
        heic_file = user_dir / "abc123.heic"
        heic_file.write_bytes(b"fake heic content")
        display_file = user_dir / "abc123_display.webp"
        display_file.write_bytes(b"pre-existing webp")

        # Create media record with display_path already set
        media = MomentMedia(
            moment_id=test_entry.moment_id,
            media_type=MediaType.IMAGE,
            mime_type="image/heic",
            upload_status=UploadStatus.PROCESSING,
            file_path=str(heic_file.relative_to(media_root)),
            display_path=str(display_file.relative_to(media_root)),
            original_filename="photo.heic",
            file_size=len(b"fake heic content"),
        )
        test_db.add(media)
        test_db.commit()
        test_db.refresh(media)

        # Mock _generate_heic_display_version to track if it's called
        with patch.object(service, "_generate_heic_display_version") as mock_gen:
            service.process_uploaded_file(
                media_id=str(media.id),
                file_path=str(heic_file),
                user_id=str(test_user.id),
            )

            mock_gen.assert_not_called()


# ─── get_media_file_for_serving: display version redirect ────────────

class TestServingHeicDisplayVersion:
    @pytest.mark.asyncio
    async def test_serves_display_version_when_present(
        self, tmp_path, test_db, test_user, test_entry
    ):
        """If display_path exists on disk, serve it instead of the original."""
        service = _build_service(tmp_path, test_db)
        media_root = tmp_path / "media"
        user_dir = media_root / str(test_user.id) / "images"
        user_dir.mkdir(parents=True)

        heic_file = user_dir / "photo.heic"
        heic_file.write_bytes(b"original heic bytes")
        display_file = user_dir / "photo_display.webp"
        display_file.write_bytes(b"webp display bytes")

        media = MomentMedia(
            moment_id=test_entry.moment_id,
            media_type=MediaType.IMAGE,
            mime_type="image/heic",
            upload_status=UploadStatus.COMPLETED,
            file_path=str(heic_file.relative_to(media_root)),
            display_path=str(display_file.relative_to(media_root)),
            original_filename="photo.heic",
            file_size=19,
        )
        test_db.add(media)
        test_db.commit()
        test_db.refresh(media)

        result = await service.get_media_file_for_serving(
            media_id=media.id,
            user_id=test_user.id,
            session=test_db,
        )

        assert result["content_type"] == "image/webp"
        assert result["file_path"] == display_file

    @pytest.mark.asyncio
    async def test_serves_original_when_no_display_path(
        self, tmp_path, test_db, test_user, test_entry
    ):
        """Without display_path, serve the original file."""
        service = _build_service(tmp_path, test_db)
        media_root = tmp_path / "media"
        user_dir = media_root / str(test_user.id) / "images"
        user_dir.mkdir(parents=True)

        heic_file = user_dir / "photo.heic"
        heic_file.write_bytes(b"original heic bytes")

        media = MomentMedia(
            moment_id=test_entry.moment_id,
            media_type=MediaType.IMAGE,
            mime_type="image/heic",
            upload_status=UploadStatus.COMPLETED,
            file_path=str(heic_file.relative_to(media_root)),
            display_path=None,
            original_filename="photo.heic",
            file_size=19,
        )
        test_db.add(media)
        test_db.commit()
        test_db.refresh(media)

        result = await service.get_media_file_for_serving(
            media_id=media.id,
            user_id=test_user.id,
            session=test_db,
        )

        assert result["file_path"] == heic_file
        # content_type should NOT be image/webp
        assert result["content_type"] != "image/webp"


# ─── delete: display version file cleanup ────────────────────────────

class TestDeleteHeicDisplayVersion:
    @pytest.mark.asyncio
    async def test_deletes_display_file_on_media_delete(
        self, tmp_path, test_db, test_user, test_entry
    ):
        """Deleting media should also remove the display version file."""
        service = _build_service(tmp_path, test_db)
        media_root = tmp_path / "media"
        user_dir = media_root / str(test_user.id) / "images"
        user_dir.mkdir(parents=True)

        heic_file = user_dir / "del.heic"
        heic_file.write_bytes(b"heic data")
        display_file = user_dir / "del_display.webp"
        display_file.write_bytes(b"webp data")

        media = MomentMedia(
            moment_id=test_entry.moment_id,
            media_type=MediaType.IMAGE,
            mime_type="image/heic",
            upload_status=UploadStatus.COMPLETED,
            file_path=str(heic_file.relative_to(media_root)),
            display_path=str(display_file.relative_to(media_root)),
            original_filename="del.heic",
            file_size=9,
        )
        test_db.add(media)
        test_db.commit()
        test_db.refresh(media)

        await service.delete_media_by_id(media.id, test_user.id, test_db)

        assert not display_file.exists()


# ─── _safe_delete_auxiliary_file ─────────────────────────────────────

class TestSafeDeleteAuxiliaryFile:
    def test_deletes_valid_file(self, tmp_path, test_db):
        service = _build_service(tmp_path, test_db)
        media_root = tmp_path / "media"
        target = media_root / "user1" / "img_display.webp"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"data")

        service._safe_delete_auxiliary_file(
            str(target.relative_to(media_root)), "display version"
        )

        assert not target.exists()

    def test_rejects_path_traversal(self, tmp_path, test_db):
        """Paths that resolve outside media_root should not be deleted."""
        service = _build_service(tmp_path, test_db)
        # Create a file outside media_root
        outside = tmp_path / "secret.txt"
        outside.write_bytes(b"secret")

        # Attempt path traversal
        service._safe_delete_auxiliary_file("../secret.txt", "test")

        # File should still exist
        assert outside.exists()

    def test_no_error_for_missing_file(self, tmp_path, test_db):
        """Should not raise if the file doesn't exist."""
        service = _build_service(tmp_path, test_db)
        service._safe_delete_auxiliary_file("nonexistent/file.webp", "test")


# ─── MediaHandler constants ──────────────────────────────────────────

class TestMediaHandlerHeicConstants:
    def test_heic_extensions_are_subset_of_image_extensions(self):
        assert MediaHandler.HEIC_EXTENSIONS.issubset(MediaHandler.IMAGE_EXTENSIONS)

    def test_heic_mime_types_include_all_variants(self):
        expected = {"image/heic", "image/heif", "image/heic-sequence", "image/heif-sequence"}
        assert MediaHandler.HEIC_MIME_TYPES == expected

    def test_media_service_delegates_to_media_handler(self):
        assert MediaService.HEIC_EXTENSIONS is MediaHandler.HEIC_EXTENSIONS
        assert MediaService.HEIC_MIME_TYPES is MediaHandler.HEIC_MIME_TYPES

    def test_heic_in_mime_type_map(self):
        assert MediaHandler.MIME_TYPE_MAP[".heic"] == "image/heic"
        assert MediaHandler.MIME_TYPE_MAP[".heif"] == "image/heif"
