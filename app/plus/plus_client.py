"""
Unified client for all Journiv Plus server communication.

TODO: Add secret refresh endpoint support when needed (future feature)
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import ValidationError
from sqlmodel import Session

from app.core.config import settings
from app.core.http_client import get_http_client
from app.core.instance import detect_platform, get_db_backend, get_or_create_instance
from app.core.logging_config import LogCategory
from app.core.signing import generate_canonical_signature
from app.models.instance_detail import InstanceDetail
from app.plus.exceptions import (
    PlusHTTPError,
    PlusIdentityRevokedError,
    PlusNetworkError,
    PlusRateLimitError,
    PlusRegistrationError,
    PlusServerError,
)
from app.schemas.license import LicenseInfoResponse, LicenseRegisterResponse
from app.schemas.version import VersionInfoResponse

logger = logging.getLogger(LogCategory.PLUS)


class PlusServerClient:
    """
    Unified client for Journiv Plus server API communication.

    Handles:
    - Instance registration (handshake)
    - Version checking
    - License operations
    - Authentication with per-instance secrets
    - Automatic re-registration on 401
    """

    def __init__(self, db: Session):
        """
        Initialize Plus server client.

        Args:
            db: Database session for loading/storing instance details
        """
        self.db = db
        self.base_url = settings.plus_server_url
        self._instance_detail: Optional[InstanceDetail] = None

    def _get_instance_detail(self) -> InstanceDetail:
        """
        Get or create instance detail record.

        Returns:
            InstanceDetail: Instance detail record

        Raises:
            PlusServerError: If database operation fails
        """
        if self._instance_detail:
            return self._instance_detail

        try:
            instance_detail = get_or_create_instance(self.db, create_if_missing=True)
            self._instance_detail = instance_detail
            return instance_detail
        except Exception as e:
            logger.error(f"Failed to get instance detail: {e}", exc_info=True)
            raise PlusServerError(f"Database error: {e}") from e

    @staticmethod
    def _safe_json(response) -> Dict[str, Any]:
        try:
            return response.json()
        except Exception:
            return {}

    async def _ensure_registered(self) -> str:
        """
        Ensure instance is registered and has a secret.

        This implements Just-In-Time (JIT) registration:
        - Checks if plus_instance_secret exists in database
        - If missing, calls Journiv Plus server POST /api/v1/instance/register
        - Saves returned secret to database
        - Returns secret for use in signing

        Returns:
            str: The instance_secret (64 hex characters)

        Raises:
            PlusRegistrationError: If registration fails
            PlusRateLimitError: If rate limited
        """
        instance_detail = self._get_instance_detail()

        # Check if already registered
        if instance_detail.plus_instance_secret:
            return instance_detail.plus_instance_secret

        # Need to register - call /api/v1/instance/register
        logger.info("Instance not registered with Plus server, initiating registration...")

        try:
            client = await get_http_client()
            platform = detect_platform()
            db_backend = get_db_backend()

            registration_payload = {
                "install_id": instance_detail.install_id,
                "journiv_version": settings.app_version,
                "platform": platform,
                "db_backend": db_backend,
            }

            # Registration endpoint does NOT require authentication (it's the handshake)
            response = await client.post(
                f"{self.base_url}/api/v1/instance/register",
                json=registration_payload,
                timeout=10.0,
            )

            if response.status_code == 429:
                # Rate limited
                detail = self._safe_json(response).get("detail", {})
                retry_after = detail.get("retry_after", 3600)
                error_msg = detail.get("detail", "Rate limit exceeded")
                logger.warning(f"Registration rate limited: {error_msg} (retry_after={retry_after}s)")
                raise PlusRateLimitError(error_msg, retry_after=retry_after)

            response_data = self._safe_json(response)

            if response.status_code != 200:
                error_detail = response_data.get("detail") or response.text or "Unknown error"
                logger.error(f"Registration failed: HTTP {response.status_code} - {error_detail}")
                raise PlusRegistrationError(f"Registration failed: {error_detail}")

            # Extract instance_secret from response
            instance_secret = response_data.get("instance_secret")
            status_value = response_data.get("status")

            if not instance_secret:
                logger.error("Registration response missing instance_secret")
                raise PlusRegistrationError("Server did not return instance_secret")
            if not re.fullmatch(r"[0-9a-f]{64}", instance_secret):
                logger.error("Registration response returned invalid instance_secret format")
                raise PlusRegistrationError("Server returned invalid instance_secret format")

            # Save secret to database
            instance_detail.plus_instance_secret = instance_secret
            self.db.commit()

            logger.info(f"Instance registration successful (status: {status_value}, install_id: {instance_detail.install_id})")
            return instance_secret

        except (PlusRateLimitError, PlusRegistrationError):
            raise
        except Exception as e:
            logger.error(f"Registration error: {e}", exc_info=True)
            raise PlusRegistrationError(f"Failed to register with Plus server: {e}") from e

    def _get_auth_headers(self, timestamp: int, signature: str) -> Dict[str, str]:
        """
        Build authentication headers for Plus server requests.

        Args:
            timestamp: Unix timestamp (seconds)
            signature: HMAC-SHA256 signature

        Returns:
            Dict[str, str]: Headers dict with X-Journiv-* headers
        """
        instance_detail = self._get_instance_detail()
        return {
            "X-Journiv-Install-ID": instance_detail.install_id,
            "X-Journiv-Timestamp": str(timestamp),
            "X-Journiv-Signature": signature,
        }

    async def _signed_request(
        self,
        method: str,
        path: str,
        body: Dict[str, Any],
        retry_on_401: bool = True,
    ) -> Dict[str, Any]:
        """
        Make a signed request to Plus server.

        Implements:
        - JIT registration check
        - HMAC signature generation
        - Header-based authentication
        - Automatic retry on 401 (re-registration)

        Returns:
            Dict[str, Any]: Response JSON

        Raises:
            PlusHTTPError: If auth fails after retry
            PlusIdentityRevokedError: If re-registration fails (blacklisted)
            PlusRateLimitError: If rate limited
            PlusNetworkError: If network/connection fails
        """
        try:
            # Ensure registered and get secret
            secret = await self._ensure_registered()

            # Generate timestamp and signature
            timestamp = int(datetime.now(timezone.utc).timestamp())
            signature = generate_canonical_signature(
                method=method,
                path=path,
                timestamp=timestamp,
                body=body,
                secret=secret,
            )

            # Build headers
            headers = self._get_auth_headers(timestamp, signature)

            # Make request
            client = await get_http_client()
            response = await client.request(
                method,
                f"{self.base_url}{path}",
                json=body,
                headers=headers,
                timeout=10.0,
            )

            # Handle 401 Unauthorized - re-register and retry
            if response.status_code == 401 and retry_on_401:
                logger.warning("Received 401 from Plus server - clearing secret and re-registering")

                # Clear secret from database
                instance_detail = self._get_instance_detail()
                instance_detail.plus_instance_secret = None
                self.db.commit()
                self._instance_detail = None  # Clear cache

                # Try re-registration
                try:
                    await self._ensure_registered()
                except PlusRegistrationError as e:
                    # Re-registration failed - instance may be blacklisted
                    logger.error(f"Re-registration failed after 401: {e}", exc_info=True)
                    raise PlusIdentityRevokedError(
                        "Instance authentication revoked. Re-registration failed. "
                        "Your instance may be blocked. Contact support."
                    ) from e

                # Retry request with new secret (recursive, but retry_on_401=False to prevent loop)
                return await self._signed_request(method, path, body, retry_on_401=False)

            # Handle 429 Rate Limit
            if response.status_code == 429:
                detail = self._safe_json(response).get("detail", {})
                retry_after = detail.get("retry_after", 3600)
                error_msg = detail.get("detail", "Rate limit exceeded")
                raise PlusRateLimitError(error_msg, retry_after=retry_after)

            # Handle other errors
            if response.status_code >= 400:
                error_detail = self._safe_json(response).get("detail") or response.text or "Unknown error"
                logger.error(f"Plus server error: HTTP {response.status_code} - {error_detail}")
                raise PlusHTTPError(response.status_code, f"Server error: {error_detail}")

            # Success
            response_data = self._safe_json(response)
            if not response_data:
                raise PlusServerError("Plus server returned invalid JSON response")
            return response_data

        except (PlusIdentityRevokedError, PlusRateLimitError, PlusServerError, PlusHTTPError):
            raise
        except Exception as e:
            logger.error(f"Network error communicating with Plus server: {e}", exc_info=True)
            raise PlusNetworkError(f"Failed to communicate with Plus server: {e}") from e

    async def check_version(self) -> VersionInfoResponse:
        """
        Check for Journiv updates.

        Calls POST /api/v1/instance/version/check

        Returns:
            VersionInfoResponse: Version check response

        Raises:
            PlusServerError: If request fails
        """
        platform = detect_platform()
        db_backend = get_db_backend()
        instance_detail = self._get_instance_detail()

        body = {
            "install_id": instance_detail.install_id,
            "journiv_version": settings.app_version,
            "platform": platform,
            "db_backend": db_backend,
        }

        response_dict = await self._signed_request("POST", "/api/v1/instance/version/check", body)

        response_dict["current_version"] = settings.app_version
        response_dict["install_id"] = instance_detail.install_id

        try:
            return VersionInfoResponse(**response_dict)
        except ValidationError as e:
            logger.error(
                f"Failed to parse version check response from Plus server: {e}. "
                f"Response: {response_dict}",
                exc_info=True
            )
            raise PlusServerError(
                f"Invalid response format from Plus server: {e}. "
                f"Expected fields: current_version, install_id, latest_version, etc."
            ) from e

    async def register_license(self, license_key: str, email: str, discord_id: Optional[str] = None) -> LicenseRegisterResponse:
        """
        Register a Journiv Plus license.

        Calls POST /api/v1/instance/license/register

        Returns:
            LicenseRegisterResponse: Registration response

        Raises:
            PlusServerError: If request fails
        """
        instance_detail = self._get_instance_detail()
        if not instance_detail.install_id:
            raise PlusServerError("install_id is not set. Instance must be initialized before license registration.")

        platform = detect_platform()
        db_backend = get_db_backend()

        body = {
            "license": license_key,
            "install_id": instance_detail.install_id,
            "email": email,
            "journiv_version": settings.app_version,
            "platform": platform,
            "db_backend": db_backend,
        }
        if discord_id:
            body["discord_id"] = discord_id

        response_dict = await self._signed_request("POST", "/api/v1/instance/license/register", body)
        return LicenseRegisterResponse(**response_dict)

    async def get_license_info(self) -> LicenseInfoResponse:
        """
        Get license information from Plus server.

        Calls POST /api/v1/instance/license/info

        Returns:
            LicenseInfoResponse: License info

        Raises:
            PlusServerError: If request fails
        """
        instance_detail = self._get_instance_detail()
        if not instance_detail.signed_license:
            raise PlusServerError("No signed license available for license info request")

        body = {
            "signed_license": instance_detail.signed_license,
            "install_id": instance_detail.install_id,
        }

        response_dict = await self._signed_request("POST", "/api/v1/instance/license/info", body)
        return LicenseInfoResponse(**response_dict)

    async def reset_license(self, install_id: str, email: str) -> Dict[str, Any]:
        """
        Reset license binding (unbind from installation).

        Calls POST /api/v1/instance/license/reset

        Returns:
            Dict with reset response

        Raises:
            PlusServerError: If request fails
        """
        body = {
            "install_id": install_id,
            "email": email,
        }

        return await self._signed_request("POST", "/api/v1/instance/license/reset", body)

    async def refresh_license(self, signed_license: str, install_id: str) -> Dict[str, Any]:
        """
        Refresh signed license to get a new one with updated expiration.

        Calls POST /api/v1/instance/license/refresh

        Returns:
            Dict with keys:
            - signed_license: New signed license (base64)
            - subscription_expires_at: Subscription expiration date (ISO format, None for lifetime)

        Raises:
            PlusServerError: If request fails
        """
        body = {
            "signed_license": signed_license,
            "install_id": install_id,
        }

        return await self._signed_request("POST", "/api/v1/instance/license/refresh", body)
