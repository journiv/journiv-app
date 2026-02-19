import zipfile

import pytest

from app.data_transfer.dayone.dayone_parser import DayOneParser


def test_parse_zip_rejects_path_traversal(tmp_path):
    """Ensure Day One ZIP extraction blocks path traversal entries."""
    bad_zip = tmp_path / "bad.zip"
    extract_dir = tmp_path / "extract"
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bad_zip, "w") as zf:
        zf.writestr("../evil.txt", "malicious")

    with pytest.raises(ValueError):
        DayOneParser.parse_zip(bad_zip, extract_dir)

    assert not (tmp_path / "evil.txt").exists()
