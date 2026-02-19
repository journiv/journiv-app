"""
Unit tests for license service behavior with per-instance auth.

Validates:
- License registration stores signed license
- License info fetches from server
- Reset uses DB install_id and always clears local state
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.instance_detail import InstanceDetail
from app.plus.exceptions import PlusNetworkError
from app.schemas.license import LicenseInfoResponse, LicenseRegisterResponse
from app.services.license_service import LicenseService


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    db = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()
    return db


@pytest.fixture
def sample_instance():
    """Create a sample instance detail."""
    instance = InstanceDetail(
        install_id="550e8400-e29b-41d4-a716-446655440100",
        signed_license=None,
        license_validated_at=None
    )
    return instance


class TestLicenseRegistration:
    """Test license registration flow."""

    @pytest.mark.asyncio
    async def test_register_stores_signed_license_without_changing_install_id(
        self, mock_db_session, sample_instance
    ):
        """Test that registration stores signed_license and keeps install_id unchanged."""
        service = LicenseService(mock_db_session)

        # Mock get_instance to return sample instance
        service.get_instance = MagicMock(return_value=sample_instance)

        mock_result = LicenseRegisterResponse(
            successful=True,
            signed_license="base64_signed_license_here",
            error_message=None
        )

        with patch('app.services.license_service.get_license_cache') as mock_cache_cls, \
            patch('app.services.license_service.PlusServerClient') as mock_client_cls:
            mock_client = mock_client_cls.return_value
            mock_client.register_license = AsyncMock(return_value=mock_result)
            mock_cache = mock_cache_cls.return_value

            result = await service.register_license(
                license_key="lic_test123abc456def7890123456789012",
                email="test@example.com"
            )

            # Verify registration was called
            mock_client.register_license.assert_called_once()

            # Verify DB install_id unchanged and license stored
            assert result["successful"] is True
            assert sample_instance.signed_license == "base64_signed_license_here"
            assert sample_instance.install_id == "550e8400-e29b-41d4-a716-446655440100"
            assert sample_instance.license_validated_at is not None
            mock_db_session.commit.assert_called_once()
            mock_cache.invalidate.assert_called_once_with(sample_instance.install_id)

    @pytest.mark.asyncio
    async def test_get_license_info_fetches_from_server(
        self, mock_db_session, sample_instance
    ):
        """Test that get_license_info fetches license info from server and caches it."""
        service = LicenseService(mock_db_session)
        service.get_instance = MagicMock(return_value=sample_instance)
        sample_instance.signed_license = "base64_signed_license_here"

        with patch('app.services.license_service.get_license_cache') as mock_cache_cls:
            mock_cache = mock_cache_cls.return_value
            mock_cache.get_info.return_value = None  # Cache miss

            with patch('app.services.license_service.PlusServerClient') as mock_client_cls:
                mock_client = mock_client_cls.return_value
                server_info = LicenseInfoResponse(
                    is_active=True,
                    tier="supporter",
                    license_type="subscription",
                    subscription_expires_at="2025-12-31T23:59:59Z",
                    install_id=sample_instance.install_id,
                    registered_email="test@example.com",
                    discord_id="987654321"
                )
                mock_client.get_license_info = AsyncMock(return_value=server_info)

                result = await service.get_license_info(refresh=True)

                # Verify server was called
                mock_client.get_license_info.assert_called_once_with()

                # Verify result was cached
                mock_cache.set_info.assert_called_once_with(
                    sample_instance.install_id,
                    server_info.model_dump()
                )

                # Verify returned data matches server response
                assert result is not None
                assert result["is_active"] is True
                assert result["tier"] == "supporter"
                assert result["license_type"] == "subscription"
                assert result["subscription_expires_at"] == "2025-12-31T23:59:59Z"
                assert result["install_id"] == sample_instance.install_id
                assert result["registered_email"] == "test@example.com"
                assert result["discord_id"] == "987654321"


class TestResetWithDbInstallId:
    """Test reset endpoint uses DB install_id."""

    @pytest.mark.asyncio
    async def test_reset_clears_local_state_on_upstream_failure(
        self, mock_db_session, sample_instance
    ):
        """Test that reset always clears local state even if upstream is unreachable."""
        service = LicenseService(mock_db_session)
        service.get_instance = MagicMock(return_value=sample_instance)
        sample_instance.signed_license = "base64_signed_license_here"

        db_install_id = sample_instance.install_id

        with patch('app.services.license_service.get_license_cache') as mock_cache_cls, \
            patch('app.services.license_service.PlusServerClient') as mock_client_cls:
            mock_client = mock_client_cls.return_value
            mock_client.reset_license = AsyncMock(side_effect=PlusNetworkError("Network down"))
            mock_cache = mock_cache_cls.return_value

            result = await service.reset_license(
                install_id=db_install_id,
                email="test@example.com"
            )

            mock_client.reset_license.assert_called_once()

            # Verify DB install_id was used (not dynamic platform_id)
            # Reset should work with DB install_id even if hardware changed
            assert sample_instance.signed_license is None  # License cleared
            mock_cache.invalidate.assert_called_once_with(db_install_id)
            assert result["status"] == "ok"
            assert result["upstream_status"] == "unknown"
            assert result["error_message"] == "Network down"
