import pytest
import typer
from unittest.mock import MagicMock, patch
from pathlib import Path
from app.cli.commands.import_cmd import import_data
from app.schemas.dto import ImportResultSummary

@pytest.fixture
def mock_dependencies():
    """Fixture to mock all external dependencies for import_data."""
    with patch("app.cli.commands.import_cmd.setup_cli_logging"), \
         patch("app.cli.commands.import_cmd.run_preflight_checks") as mock_preflight, \
         patch("app.cli.commands.import_cmd.ZipHandler") as mock_zip_handler, \
         patch("app.cli.commands.import_cmd.Session") as mock_session, \
         patch("app.cli.commands.import_cmd.UserService") as mock_user_service, \
         patch("app.cli.commands.import_cmd.ImportService") as mock_import_service, \
         patch("app.cli.commands.import_cmd.confirm_action", return_value=True), \
         patch("app.cli.commands.import_cmd.display_import_summary") as mock_display, \
         patch("app.cli.commands.import_cmd.GracefulInterruptHandler") as mock_sig_handler, \
         patch("app.cli.commands.import_cmd.console") as mock_console, \
         patch("app.cli.commands.import_cmd.settings") as mock_settings, \
         patch("builtins.open") as mock_open:

        # Mock settings
        mock_settings.media_root = "/tmp/media"

        # Setup mock behavior for context managers
        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db

        mock_handler_instance = MagicMock()
        mock_handler_instance.interrupted = False
        mock_sig_handler.return_value.__enter__.return_value = mock_handler_instance

        # Mock preflight and validation
        mock_preflight.return_value = {"all_passed": True}
        mock_zip_handler.validate_zip_structure.return_value = {
            "valid": True,
            "file_count": 10,
            "data_file_found": True
        }

        # Mock user lookup
        mock_user = MagicMock()
        mock_user.id = "user-id"
        mock_user.email = "test@example.com"
        mock_user_service.return_value.get_user_by_email.return_value = mock_user

        # Mock import job creation
        mock_job = MagicMock()
        mock_job.id = "job-id"
        mock_import_service.return_value.create_import_job.return_value = mock_job

        # Mock file extraction
        mock_zip_handler.stream_extract.return_value = {
            "data_file": Path("data.json"),
            "media_dir": Path("media"),
            "total_size": 100,
            "file_count": 10,
            "warnings": [],
            "warning_categories": {}
        }

        # Mock summary result
        mock_summary = ImportResultSummary(entries_created=5)
        mock_import_service.return_value.import_journiv_data.return_value = mock_summary
        mock_import_service.return_value.import_dayone_data.return_value = mock_summary

        # Mock data.json reading
        mock_open.return_value.__enter__.return_value.read.return_value = '{"journals": []}'

        yield {
            "mock_display": mock_display,
            "mock_zip_handler": mock_zip_handler,
            "mock_import_service": mock_import_service,
            "mock_console": mock_console
        }

def test_import_data_journiv_success(mock_dependencies):
    """Test successful Journiv import logic flow."""
    import_data(
        file_path=Path(__file__),
        user_email="test@example.com",
        source_type="journiv",
        dry_run=False,
        skip_preflight=False,
        force=False,
        skip_media_validation=False,
        max_entry_size_mb=50000,
        verbose=False
    )

    mock_dependencies["mock_display"].assert_called_once()
    mock_dependencies["mock_import_service"].return_value.import_journiv_data.assert_called_once()

def test_import_data_dayone_success(mock_dependencies):
    """Test successful Day One import logic flow."""
    import_data(
        file_path=Path(__file__),
        user_email="test@example.com",
        source_type="dayone",
        dry_run=False,
        skip_preflight=False,
        force=False,
        skip_media_validation=False,
        max_entry_size_mb=50000,
        verbose=False
    )

    mock_dependencies["mock_display"].assert_called_once()
    mock_dependencies["mock_import_service"].return_value.import_dayone_data.assert_called_once()

    # Verify extraction_dir (temp_path) and media_dir were passed
    args, kwargs = mock_dependencies["mock_import_service"].return_value.import_dayone_data.call_args
    assert "extraction_dir" in kwargs
    assert kwargs["extraction_dir"] is not None
    assert "media_dir" in kwargs
    assert kwargs["media_dir"] is not None
