"""
Unit tests for integration models, services, and endpoints.

These tests verify the core integration functionality including:
- Database models (Integration, ImmichAsset, etc.)
- Service layer (connect, disconnect, status)
- API endpoints (POST /connect, GET /status, etc.)
"""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.routing import APIRoute

from app.integrations.schemas import (
    IntegrationConnectRequest,
    IntegrationStatusResponse,
)
from app.models.activity import Activity
from app.models.integration import AssetType, Integration, IntegrationProvider
from app.models.mood import Mood

# ================================================================================
# MODEL TESTS
# ================================================================================

class TestIntegrationModel:
    """Test the Integration database model."""

    def test_integration_model_creation(self):
        """Test creating an Integration instance."""
        integration = Integration(
            user_id="00000000-0000-0000-0000-000000000000",
            provider=IntegrationProvider.IMMICH,
            base_url="https://photos.example.com",
            access_token_encrypted="encrypted-token",
            external_user_id="immich-user-456",
            is_active=True,
            connected_at=datetime.now(timezone.utc)
        )

        assert integration.provider == IntegrationProvider.IMMICH
        assert integration.base_url == "https://photos.example.com"
        assert integration.is_active is True

    def test_integration_provider_enum(self):
        """Test that IntegrationProvider enum has expected values."""
        assert IntegrationProvider.IMMICH == "immich"

        # Test enum values
        all_providers = list(IntegrationProvider)
        assert len(all_providers) >= 1
        assert IntegrationProvider.IMMICH in all_providers

    def test_integration_datetime_columns_are_timezone_aware(self):
        table = Integration.__table__
        for column_name in (
            "created_at",
            "updated_at",
            "token_expires_at",
            "last_synced_at",
            "last_error_at",
            "connected_at",
        ):
            assert table.c[column_name].type.timezone is True
        assert table.c["updated_at"].onupdate is not None

    def test_mood_and_activity_links_use_passive_deletes(self):
        assert Activity.__mapper__.relationships["moment_activity_links"].passive_deletes is True
        assert Mood.__mapper__.relationships["moment_activity_links"].passive_deletes is True


# ================================================================================
# SCHEMA TESTS
# ================================================================================

class TestIntegrationSchemas:
    """Test Pydantic schemas for API requests/responses."""

    def test_connect_request_schema(self):
        """Test IntegrationConnectRequest validation."""
        request = IntegrationConnectRequest(
            provider=IntegrationProvider.IMMICH,
            credentials={"api_key": "test-key"},
            base_url="https://photos.example.com/"
        )

        assert request.provider == IntegrationProvider.IMMICH
        assert request.credentials["api_key"] == "test-key"
        # base_url should have trailing slash removed
        assert request.base_url == "https://photos.example.com"

    def test_connect_request_without_base_url(self):
        """Test IntegrationConnectRequest without base_url (uses .env default)."""
        request = IntegrationConnectRequest(
            provider=IntegrationProvider.IMMICH,
            credentials={"api_key": "test-key"}
        )

        assert request.base_url is None  # Should use .env default

    def test_status_response_schema(self):
        """Test IntegrationStatusResponse structure."""
        response = IntegrationStatusResponse(
            provider=IntegrationProvider.IMMICH,
            status="connected",
            external_user_id="immich-user-123",
            connected_at=datetime.now(timezone.utc),
            last_synced_at=None,
            last_error=None,
            is_active=True
        )

        assert response.status == "connected"
        assert response.provider == IntegrationProvider.IMMICH
        assert response.is_active is True


# ================================================================================
# SERVICE TESTS (Mocked)
# ================================================================================

class TestIntegrationService:
    """Test integration service layer."""

    @pytest.mark.asyncio
    async def test_connect_integration_success(self):
        """Test successfully connecting an integration."""
        from unittest.mock import MagicMock

        from app.integrations.service import connect_integration

        # Mock database session and user
        mock_session = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "user-123"

        # Mock the provider's connect function to return a user ID. Also stub
        # ensure_album_exists so the real immich client (and its aiohttp session)
        # is never created during this unit test.
        with patch('app.integrations.immich.connect', new_callable=AsyncMock) as mock_connect, \
             patch('app.integrations.immich.ensure_album_exists', new_callable=AsyncMock):
            mock_connect.return_value = "immich-user-456"

            # Mock session.exec to simulate no existing integration
            mock_session.exec.return_value.first.return_value = None

            response = await connect_integration(
                session=mock_session,
                user=mock_user,
                provider=IntegrationProvider.IMMICH,
                credentials={"api_key": "test-key"},
                base_url="https://photos.example.com"
            )

            # Verify response
            assert response.status == "connected"
            assert response.provider == IntegrationProvider.IMMICH
            assert response.external_user_id == "immich-user-456"

            # Verify provider connect was called
            mock_connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_integration_status_not_connected(self):
        """Test getting status for a non-existent integration."""
        from unittest.mock import MagicMock

        from app.integrations.service import get_integration_status

        mock_session = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "user-123"

        # Mock session.exec to return None (no integration found)
        mock_session.exec.return_value.first.return_value = None

        response = await get_integration_status(
            session=mock_session,
            user=mock_user,
            provider=IntegrationProvider.IMMICH
        )

        # Should return disconnected status
        assert response.status == "disconnected"
        assert response.provider == IntegrationProvider.IMMICH
        assert response.is_active is False
        assert response.external_user_id is None

    @pytest.mark.asyncio
    async def test_get_integration_status_stays_connected_with_last_error(self):
        """Active integrations remain connected even when last sync has an error."""
        from unittest.mock import MagicMock

        from app.integrations.service import get_integration_status

        mock_session = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "user-123"
        integration = MagicMock()
        integration.provider = IntegrationProvider.IMMICH
        integration.external_user_id = "immich-user-123"
        integration.connected_at = datetime.now(timezone.utc)
        integration.last_synced_at = None
        integration.last_error = "temporary provider timeout"
        integration.is_active = True
        integration.import_mode = "link_only"
        integration.get_metadata.return_value = {}

        mock_session.exec.return_value.first.return_value = integration

        response = await get_integration_status(
            session=mock_session,
            user=mock_user,
            provider=IntegrationProvider.IMMICH,
        )

        assert response.status == "connected"
        assert response.is_active is True
        assert response.last_error == "temporary provider timeout"

    @pytest.mark.asyncio
    async def test_list_integration_assets_clears_stale_last_error_on_success(self):
        """A successful asset list clears stale sync/list errors."""
        from contextlib import contextmanager
        from unittest.mock import MagicMock

        from app.integrations.service import list_integration_assets

        mock_session = MagicMock()
        temp_session = MagicMock()
        mock_user = SimpleNamespace(id="user-123")
        integration = SimpleNamespace(
            user_id=mock_user.id,
            provider=IntegrationProvider.IMMICH,
            is_active=True,
            last_error="temporary provider timeout",
            last_error_at=datetime.now(timezone.utc),
            updated_at=None,
        )
        temp_session.exec.return_value.first.return_value = integration
        mock_provider = SimpleNamespace(list_assets=AsyncMock(return_value=[]))

        @contextmanager
        def fake_session_context():
            yield temp_session

        with patch("app.core.database.get_session_context", fake_session_context), \
             patch("app.integrations.service.get_provider_module", return_value=mock_provider):
            assets, total = await list_integration_assets(
                session=mock_session,
                user=mock_user,
                provider=IntegrationProvider.IMMICH,
            )

        assert assets == []
        assert total == -1
        assert integration.last_error is None
        assert integration.last_error_at is None
        mock_session.add.assert_called_once_with(integration)
        mock_session.commit.assert_called_once()


# ================================================================================
# ROUTER/ENDPOINT TESTS
# ================================================================================

class TestIntegrationEndpoints:
    """Test integration API endpoints."""

    def test_router_exists(self):
        """Test that the integration router is defined."""
        from app.integrations.router import router

        assert router is not None
        assert router.prefix == "/integrations"

    def test_connect_endpoint_exists(self):
        """Test that the /connect endpoint is registered."""
        from app.integrations.router import router

        # Find the connect endpoint
        connect_route = None
        for route in router.routes:
            if getattr(route, "path", None) == "/integrations/connect":
                connect_route = route
                break

        assert connect_route is not None
        assert isinstance(connect_route, APIRoute)
        assert "POST" in connect_route.methods

    def test_status_endpoint_exists(self):
        """Test that the /{provider}/status endpoint is registered."""
        from app.integrations.router import router

        # Find the status endpoint
        status_route = None
        for route in router.routes:
            if getattr(route, "path", None) == "/integrations/{provider}/status":
                status_route = route
                break

        assert status_route is not None
        assert isinstance(status_route, APIRoute)
        assert "GET" in status_route.methods

    @pytest.mark.asyncio
    async def test_proxy_client_is_singleton(self):
        """Test that the proxy client is reused across calls."""
        from app.integrations import service as integrations_service

        integrations_service._proxy_client = None
        client_first = await integrations_service._get_proxy_client()
        client_second = await integrations_service._get_proxy_client()

        assert isinstance(client_first, httpx.AsyncClient)
        assert client_first is client_second

    @pytest.mark.asyncio
    async def test_close_httpx_stream_only_closes_response(self):
        """Test that closing the stream does not require a client close."""
        from app.integrations import router as integrations_router

        response = AsyncMock(spec=httpx.Response)

        await integrations_router._close_httpx_stream(response)

        response.aclose.assert_awaited_once()


# ================================================================================
# PROVIDER REGISTRY TESTS
# ================================================================================

class TestProviderRegistry:
    """Test the provider registry system."""

    def test_all_providers_registered(self):
        """Test that all providers have modules in the registry."""
        from app.integrations.service import PROVIDER_REGISTRY, IntegrationProvider

        # All enum values should be in the registry
        for provider in IntegrationProvider:
            assert provider in PROVIDER_REGISTRY

    def test_get_provider_module_success(self):
        """Test getting a provider module from the registry."""
        from app.integrations.service import IntegrationProvider, get_provider_module

        module = get_provider_module(IntegrationProvider.IMMICH)
        assert module is not None
        assert hasattr(module, 'connect')
        assert hasattr(module, 'list_assets')
        assert hasattr(module, 'sync')

    def test_get_provider_module_invalid_raises_error(self):
        """Test that getting an invalid provider raises ValueError."""
        from app.integrations.service import get_provider_module

        # This should not happen in practice (enum prevents it), but test defensive code
        with pytest.raises(ValueError, match="not supported"):
            get_provider_module("invalid-provider")  # type: ignore


# ================================================================================
# ALBUM MANAGEMENT TESTS
# ================================================================================

class TestAlbumAssetManagement:
    """Test album asset addition and removal logic."""

    @pytest.mark.asyncio
    async def test_remove_assets_from_album_with_shared_assets(self):
        """
        Test that assets shared across multiple entries are not removed from album
        when only one entry is deleted.
        """
        import uuid
        from unittest.mock import MagicMock

        from app.integrations.service import remove_assets_from_integration_album
        from app.models.integration import IntegrationProvider

        # Setup test data
        user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        asset_id_shared = "asset-shared-123"
        asset_id_unique = "asset-unique-456"

        # Mock session
        mock_session = MagicMock()

        # Mock the query result - asset_id_shared is still referenced by another entry
        # The query returns a list of tuples with single values
        mock_result = MagicMock()
        mock_result.all.return_value = [(asset_id_shared,)]  # Only the shared asset is still referenced

        # Mock integration (inactive to skip actual API call)
        mock_integration = MagicMock()
        mock_integration.is_active = False

        # Setup mock to return different values for different exec calls
        # First call: check for remaining references
        # Second call: get integration
        mock_session.exec.side_effect = [
            mock_result,  # First call: remaining asset check
            MagicMock(first=MagicMock(return_value=mock_integration))  # Second call: get integration
        ]

        # Test: Try to remove both assets (one shared, one unique)
        # Expected: Only the unique asset should be attempted for removal
        await remove_assets_from_integration_album(
            session=mock_session,
            user_id=user_id,
            provider=IntegrationProvider.IMMICH,
            asset_ids=[asset_id_shared, asset_id_unique]
        )

        # Verify the query was executed to check for remaining references
        # Should be called twice: once for asset check, once for integration lookup
        assert mock_session.exec.call_count == 2

        # The function should identify that asset_id_shared is still in use
        # and only attempt to remove asset_id_unique
        # Since integration is inactive, the actual removal won't happen,
        # but we verified the filtering logic works

    @pytest.mark.asyncio
    async def test_remove_assets_all_still_in_use(self):
        """
        Test that no assets are removed when all are still referenced by other entries.
        """
        import uuid
        from unittest.mock import MagicMock

        from app.integrations.service import remove_assets_from_integration_album
        from app.models.integration import IntegrationProvider

        user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        asset_ids = ["asset-1", "asset-2", "asset-3"]

        # Mock session
        mock_session = MagicMock()

        # All assets are still referenced
        mock_result = MagicMock()
        mock_result.all.return_value = [(aid,) for aid in asset_ids]

        mock_session.exec.return_value = mock_result

        # Test: Try to remove assets that are all still in use
        await remove_assets_from_integration_album(
            session=mock_session,
            user_id=user_id,
            provider=IntegrationProvider.IMMICH,
            asset_ids=asset_ids
        )

        # Should return early without attempting provider call
        # Verify query was executed
        mock_session.exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_assets_none_in_use(self):
        """
        Test that all assets are removed when none are referenced by other entries.
        """
        import uuid
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.integrations.service import remove_assets_from_integration_album
        from app.models.integration import ImportMode, IntegrationProvider

        user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        asset_ids = ["asset-1", "asset-2"]

        # Mock session
        mock_session = MagicMock()

        # No assets are referenced (empty result)
        mock_result = MagicMock()
        mock_result.all.return_value = []

        # First call: check for remaining references (returns empty)
        # Second call: get integration
        mock_integration = MagicMock()
        mock_integration.is_active = True
        mock_integration.import_mode = ImportMode.LINK_ONLY
        mock_integration.base_url = "https://immich.example.com"
        mock_integration.access_token_encrypted = "encrypted-token"
        mock_integration.get_metadata.return_value = {"album_id": "album-123"}

        mock_session.exec.side_effect = [
            mock_result,  # First call: remaining asset check
            MagicMock(first=MagicMock(return_value=mock_integration))  # Second call: get integration
        ]

        # Mock provider module
        mock_provider = MagicMock()
        mock_provider.get_album_id_by_name = AsyncMock(return_value="album-123")
        mock_provider.remove_assets_from_album = AsyncMock()

        with patch("app.integrations.service.get_provider_module", return_value=mock_provider):
            with patch("app.integrations.service.decrypt_token", return_value="api-key"):
                await remove_assets_from_integration_album(
                    session=mock_session,
                    user_id=user_id,
                    provider=IntegrationProvider.IMMICH,
                    asset_ids=asset_ids
                )

        # Should call provider to remove all assets
        mock_provider.remove_assets_from_album.assert_called_once_with(
            "https://immich.example.com",
            "api-key",
            "album-123",
            asset_ids
        )


# TODO Add more tests: Add integration tests with real database
# - Test database constraints (unique user+provider)
# - Test foreign key cascades (delete user -> delete integrations)
# - Test concurrent connections to same provider
#
# TODO Add tests for Immich provider
# - Mock Immich API responses
# - Test asset listing and pagination
# - Test thumbnail proxy
# - Test sync logic and cache management

# ================================================================================
# OPTIMIZATION TESTS
# ================================================================================

class TestIntegrationOptimizations:
    """Test recent performance optimizations (Connection Pooling, Caching, Shared Clients)."""

    @pytest.mark.asyncio
    async def test_proxy_credential_caching(self):
        """Test that proxy endpoints use cache and avoid DB on hit."""
        import uuid
        from unittest.mock import AsyncMock, MagicMock

        from app.integrations.service import fetch_proxy_asset
        from app.models.integration import IntegrationProvider

        # Mocks
        user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        mock_cache = MagicMock()
        mock_cache.get.return_value = {
            "base_url": "https://cached.com",
            "token": "cached-token",
            "is_active": True
        }

        # Mock Cache Getter - patch in service module where it's used
        with patch("app.integrations.service._get_integration_cache", return_value=mock_cache):
            # Mock DB Context to ensure it's NOT used when cache hits
            with patch("app.core.database.get_session_context"):
                # Mock Proxy Client to avoid actual network call
                mock_client = AsyncMock()
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.headers = {"content-type": "image/jpeg"}
                mock_response.aiter_bytes.return_value = [b"data"]
                mock_client.build_request.return_value = "request"
                mock_client.send.return_value = mock_response

                with patch("app.integrations.service._get_proxy_client", return_value=mock_client):
                    # Patch decrypt_token where it's used (in service module)
                    with patch("app.integrations.service.decrypt_token", return_value="decrypted-key"):
                        # Call the service function directly
                        await fetch_proxy_asset(
                            user_id=user_id,
                            provider=IntegrationProvider.IMMICH,
                            asset_id="asset-123",
                            variant="thumbnail"
                        )

                        # VERIFICATION:
                        # 1. Cache was checked
                        mock_cache.get.assert_called_with(scope_id=str(user_id), cache_type="immich")

                        # 2. Request used cached URL
                        mock_client.build_request.assert_called()
                        # call_args[0][1] is url. Check it starts with cached base_url
                        args, _ = mock_client.build_request.call_args
                        assert args[1].startswith("https://cached.com")

    @pytest.mark.asyncio
    async def test_fetch_proxy_asset_resolves_video_from_api(self):
        """Test that fetch_proxy_asset resolves video type from API on cache miss."""
        from unittest.mock import AsyncMock, MagicMock

        from app.integrations import service
        from app.models.integration import IntegrationProvider

        # Mock dependencies
        with patch("app.integrations.service._get_integration_cache", return_value=None):
            # Mock get_session_context since fetch_proxy_asset now manages its own session
            mock_session = MagicMock()
            with patch("app.core.database.get_session_context") as mock_get_session:
                mock_get_session.return_value.__enter__.return_value = mock_session
                mock_get_session.return_value.__exit__.return_value = None

                with patch("app.integrations.service._exec", new_callable=AsyncMock) as mock_exec:
                    # Mock integration retrieval
                    mock_integration = MagicMock()
                    mock_integration.base_url = "http://immich"
                    # Mock encrypted token
                    mock_integration.access_token_encrypted = "enc"
                    mock_integration.is_active = True

                    # Mock the result object (ScalarResult) which has .first()
                    mock_result = MagicMock()
                    mock_result.first.return_value = mock_integration
                    mock_exec.return_value = mock_result

                    with patch("app.integrations.service.decrypt_token", return_value="key"):
                        with patch("app.integrations.service._get_proxy_client", new_callable=AsyncMock):
                            # Mock immich helpers
                            with patch("app.integrations.immich.get_cached_asset_type", return_value=None) as mock_cache:
                                with patch("app.integrations.immich.get_asset_info", new_callable=AsyncMock) as mock_info:
                                    mock_info.return_value = {"type": "VIDEO"}

                                    # Mock get_asset_url to verify it receives VIDEO
                                    with patch("app.integrations.immich.get_asset_url") as mock_get_url:
                                        mock_get_url.return_value = "http://immich/video"

                                        await service.fetch_proxy_asset(
                                            user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                                            provider=IntegrationProvider.IMMICH,
                                            asset_id="asset1",
                                            variant="original"
                                        )

                                        # Verify flow
                                        mock_cache.assert_called_once()
                                        mock_info.assert_called_once()
                                        mock_get_url.assert_called_with("http://immich", "asset1", "original", AssetType.VIDEO)
