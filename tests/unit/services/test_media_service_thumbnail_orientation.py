"""Image thumbnails must honour EXIF orientation (issue #635)."""
from pathlib import Path
from unittest.mock import MagicMock

from PIL import Image

from app.services.media_service import MediaService


def _make_service() -> MediaService:
    return MediaService(session=MagicMock())


def _write_jpeg(path: Path, size: tuple[int, int], orientation: int | None) -> None:
    img = Image.new("RGB", size, "red")
    exif = Image.Exif()
    if orientation is not None:
        exif[0x0112] = orientation
    img.save(path, "JPEG", exif=exif)


def test_thumbnail_applies_exif_rotation(tmp_path):
    # Stored landscape (200x100) with orientation 6 => displays as portrait (100x200).
    src = tmp_path / "photo.jpg"
    thumb = tmp_path / "thumb.jpg"
    _write_jpeg(src, (200, 100), 6)

    _make_service()._generate_image_thumbnail(src, thumb)

    with Image.open(thumb) as out:
        assert out.height > out.width


def test_thumbnail_without_exif_unchanged(tmp_path):
    src = tmp_path / "photo.jpg"
    thumb = tmp_path / "thumb.jpg"
    _write_jpeg(src, (200, 100), None)

    _make_service()._generate_image_thumbnail(src, thumb)

    with Image.open(thumb) as out:
        assert out.width > out.height


def test_dimensions_swapped_for_rotated_exif(tmp_path):
    src = tmp_path / "photo.jpg"
    _write_jpeg(src, (200, 100), 6)

    assert _make_service()._get_image_dimensions(src) == {"width": 100, "height": 200}


def test_dimensions_unchanged_without_exif(tmp_path):
    src = tmp_path / "photo.jpg"
    _write_jpeg(src, (200, 100), None)

    assert _make_service()._get_image_dimensions(src) == {"width": 200, "height": 100}
