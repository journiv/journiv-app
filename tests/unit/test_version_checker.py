from unittest.mock import MagicMock, patch

from app.services.version_checker import VersionChecker


def test_get_instance_info_delegates_to_system():
    """Test that get_instance_info calls the core system utility."""
    mock_db = MagicMock()

    with patch("app.services.version_checker.get_system_info") as mock_get_info:
        expected_info = {
            "journiv_version": "1.0.0",
            "platform": "test_plat",
            "db_backend": "test_db"
        }
        mock_get_info.return_value = expected_info

        checker = VersionChecker(db=mock_db)
        result = checker.get_instance_info()

        assert result == expected_info
        mock_get_info.assert_called_once()
