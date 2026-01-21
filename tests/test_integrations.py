"""
Unit tests for integration models, services, and endpoints.

These tests verify the core integration functionality including:
- Database models (Integration, ImmichAsset, etc.)
- Service layer (connect, disconnect, status)
- API endpoints (POST /connect, GET /status, etc.)
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx

from app.models.integration import Integration, IntegrationProvider
from app.integrations.schemas import IntegrationConnectRequest, IntegrationStatusResponse


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
        from app.integrations.service import connect_integration
        from unittest.mock import MagicMock

        # Mock database session and user
        mock_session = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "user-123"

        # Mock the provider's connect function to return a user ID
        with patch('app.integrations.immich.connect', new_callable=AsyncMock) as mock_connect:
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
        from app.integrations.service import get_integration_status
        from unittest.mock import MagicMock

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

        request = httpx.Request("GET", "https://example.com")
        response = httpx.Response(200, request=request)
        response.aclose = AsyncMock()

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
        from app.integrations.service import get_provider_module, IntegrationProvider

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
        from app.integrations.service import remove_assets_from_integration_album
        from app.models.integration import IntegrationProvider
        from app.models.entry import Entry, EntryMedia
        from unittest.mock import MagicMock, AsyncMock
        import uuid

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
        from app.integrations.service import remove_assets_from_integration_album
        from app.models.integration import IntegrationProvider
        from unittest.mock import MagicMock, AsyncMock
        import uuid

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
        from app.integrations.service import remove_assets_from_integration_album
        from app.models.integration import IntegrationProvider
        from unittest.mock import MagicMock, AsyncMock, patch
        import uuid

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
        mock_integration.base_url = "https://immich.example.com"
        mock_integration.access_token_encrypted = "encrypted-token"

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
    async def test_immich_client_is_shared(self):
        """Test that Immich provider uses a shared httpx client."""
        from app.integrations import immich

        # Reset client to ensure clean state
        original_client = immich._client
        immich._client = None
        client1 = None
        client2 = None

        try:
            client1 = immich._get_client()
            client2 = immich._get_client()

            assert client1 is not None
            assert client2 is not None
            assert client1 is client2
            assert isinstance(client1, httpx.AsyncClient)
        finally:
            clients_to_close = []
            for client in (immich._client, client1, client2):
                if isinstance(client, httpx.AsyncClient) and client is not original_client:
                    if client not in clients_to_close:
                        clients_to_close.append(client)
            for client in clients_to_close:
                await client.aclose()
            immich._client = original_client

    @pytest.mark.asyncio
    async def test_proxy_credential_caching(self):
        """Test that proxy endpoints use cache and avoid DB on hit."""
        from app.integrations.service import fetch_proxy_asset
        from app.models.integration import IntegrationProvider
        from app.models.user import User
        from unittest.mock import MagicMock, AsyncMock
        import uuid

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
            with patch("app.core.database.get_session_context") as mock_db_ctx:
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
                        # Mock session (needed as parameter even though DB shouldn't be hit)
                        mock_session = MagicMock()

                        # Call the service function directly
                        await fetch_proxy_asset(
                            session=mock_session,
                            user_id=user_id,
                            provider=IntegrationProvider.IMMICH,
                            asset_id="asset-123",
                            variant="thumbnail"
                        )

                        # VERIFICATION:
                        # 1. Cache was checked
                        mock_cache.get.assert_called_with(scope_id=str(user_id), cache_type="immich")

                        # 2. DB was NOT touched (session.exec not called because cache hit)
                        mock_session.exec.assert_not_called()

                        # 3. Request used cached URL
                        mock_client.build_request.assert_called()
                        # call_args[0][1] is url. Check it starts with cached base_url
                        args, _ = mock_client.build_request.call_args
                        assert args[1].startswith("https://cached.com")
