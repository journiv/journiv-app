from pathlib import Path

from app.utils.import_export.temp_paths import get_import_temp_root, import_temp_directory


def test_get_import_temp_root_uses_existing_configured_directory(monkeypatch, tmp_path):
    configured_root = tmp_path / "imports" / "temp"
    configured_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.core.config.settings.import_temp_dir", str(configured_root))

    root = get_import_temp_root()

    assert root == configured_root.resolve()
    assert root.exists()
    assert root.is_dir()


def test_import_temp_directory_is_created_under_configured_root(monkeypatch, tmp_path):
    configured_root = tmp_path / "imports" / "temp"
    configured_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.core.config.settings.import_temp_dir", str(configured_root))

    with import_temp_directory(prefix="test-") as temp_dir:
        assert temp_dir.exists()
        assert temp_dir.resolve().is_relative_to(configured_root.resolve())


def test_get_import_temp_root_creates_when_missing(monkeypatch, tmp_path):
    configured_root = tmp_path / "imports" / "missing-temp"
    monkeypatch.setattr("app.core.config.settings.import_temp_dir", str(configured_root))

    root = get_import_temp_root()

    assert root == configured_root.resolve()
    assert root.exists()
    assert root.is_dir()
