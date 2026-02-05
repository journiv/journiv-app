"""
License service for managing Journiv Plus licenses.

This service handles license operations and instance management.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlmodel import Session

from app.core.exceptions import (
    LicenseResetEmailMismatchError,
    LicenseResetInstallIdMismatchError,
    LicenseResetRateLimitedError,
)
from app.core.instance import get_instance_strict
from app.core.license_cache import get_license_cache
from app.core.logging_config import LogCategory
from app.models.instance_detail import InstanceDetail
from app.plus.exceptions import (
    PlusHTTPError,
    PlusNetworkError,
    PlusRateLimitError,
    PlusRegistrationError,
    PlusServerError,
)
from app.plus.plus_client import PlusServerClient

logger = logging.getLogger(LogCategory.APP)


class LicenseService:
    """
    Service for managing licenses and instance details.
    """

    def __init__(self, db: Session):
        """
        Initialize license service.

        Args:
            db: Database session
        """
        self.db = db

    def get_instance(self) -> InstanceDetail:
        """
        Get the singleton instance details row.

        Assumes the instance row and install_id are created during startup.
        Raises if missing to avoid silently generating new IDs at runtime.
        """
        return get_instance_strict(self.db)

    async def register_license(
        self,
        license_key: str,
        email: str,
        discord_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Register a Journiv Plus license to this installation.

        The client sends the current install_id (platform_id) to the server for binding.

        Args:
            license_key: Plain text license key
            email: User's email address
            discord_id: Optional Discord ID

        Returns:
            Dict with keys: successful, signed_license, error_message
        """
        instance = self.get_instance()

        # Register license with Journiv Plus
        client = PlusServerClient(self.db)
        try:
            result = await client.register_license(
                license_key=license_key,
                email=email,
                discord_id=discord_id
            )
        except PlusRateLimitError as e:
            retry_minutes = max(1, e.retry_after // 60) if e.retry_after else 60
            return {
                "successful": False,
                "signed_license": None,
                "error_message": f"Rate limit exceeded. Please try again in {retry_minutes} minutes.",
                "rate_limited": True,
                "retry_after": e.retry_after
            }
        except (PlusNetworkError, PlusRegistrationError) as e:
            logger.error(f"License registration failed: {e}")
            return {
                "successful": False,
                "signed_license": None,
                "error_message": f"Failed to connect to license server: {e}"
            }
        except PlusServerError as e:
            logger.error(f"License server error: {e}")
            return {
                "successful": False,
                "signed_license": None,
                "error_message": str(e)
            }

        # Store signed license if successful and signed_license is present
        if result.successful:
            signed_license = result.signed_license
            if signed_license:
                instance.signed_license = signed_license
                instance.license_validated_at = datetime.now(timezone.utc)
                self.db.commit()
                self.db.refresh(instance)

                cache = get_license_cache()
                cache.invalidate(instance.install_id)
            else:
                logger.error(
                    "License registration returned successful=True but signed_license is missing. "
                    "This indicates a server-side issue."
                )
                return {
                    "successful": False,
                    "signed_license": None,
                    "error_message": "License registration succeeded but server did not return a signed license."
                }

        return result.model_dump()

    async def get_license_info(
        self,
        refresh: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed license information from journiv-plus server.

        This method fetches license information for UI display purposes only.
        It does NOT perform license validation - that happens in the compiled module.
        For license enforcement, use the get_plus_factory dependency in API endpoints.

        Args:
            refresh: If True, bypasses cache and fetches fresh data from server

        Returns:
            License info dict from server, or None if no license is registered
        """
        instance = self.get_instance()

        # No license registered
        if not instance.signed_license:
            return None

        # Check cache if not refreshing
        if not refresh:
            cache = get_license_cache()
            cached_info = cache.get_info(instance.install_id)
            if cached_info:
                logger.debug(f"Returning cached license info for install_id={instance.install_id}")
                return cached_info

        # Fetch from journiv-plus server
        try:
            client = PlusServerClient(self.db)
            server_info_model = await client.get_license_info()
            server_info = server_info_model.model_dump()

            # Cache the result
            cache = get_license_cache()
            cache.set_info(instance.install_id, server_info)

            logger.debug(f"Fetched and cached license info from server for install_id={instance.install_id}")
            return server_info

        except (PlusNetworkError, PlusRegistrationError, PlusServerError) as e:
            logger.error(f"Failed to fetch license info from server: {e}")
            return None

    async def reset_license(
        self,
        install_id: str,
        email: str
    ) -> Dict[str, Any]:
        """
        Unbind license from current installation (local state cleanup).

        CRITICAL BEHAVIOR:
        - Always clears local license state (authoritative)
        - Attempts upstream unbind (best effort, can fail)
        - Never blocks on network errors
        - Idempotent (safe to call multiple times)

        Args:
            install_id: Current installation ID to unbind (must match instance)
            email: User's email for verification

        Returns:
            Dict with keys:
            - status (str): "ok" for success
            - error_message (str|None): Error if upstream call failed (for logging)
            - upstream_status (str): Status of upstream unbind call

        Raises:
            HTTPException: If email mismatch (403) or rate limit (429) from upstream
        """
        instance = self.get_instance()

        # Verify install_id matches (security check)
        if instance.install_id != install_id:
            logger.error(
                f"Reset attempt with mismatched install_id: "
                f"request={install_id}, actual={instance.install_id}"
            )
            raise LicenseResetInstallIdMismatchError(
                "install_id does not match this installation"
            )

        # Check if license exists locally
        has_license = instance.signed_license is not None

        # Attempt upstream unbind (best effort, can fail)
        upstream_status = "unknown"
        upstream_error = None
        try:
            client = PlusServerClient(self.db)
            upstream_result = await client.reset_license(install_id=install_id, email=email)
            upstream_status = upstream_result.get("status", "success")
            logger.info(f"Upstream unbind successful for install_id={install_id}")
        except PlusRateLimitError as e:
            logger.warning(f"Upstream unbind rate limited for install_id={install_id}")
            raise LicenseResetRateLimitedError(e.retry_after or 3600) from e
        except PlusHTTPError as e:
            upstream_error = str(e)
            if e.status_code == 403:
                logger.warning(f"Upstream unbind email mismatch for install_id={install_id}")
                raise LicenseResetEmailMismatchError(
                    upstream_error or "Email verification failed"
                ) from e
            logger.warning(
                f"Upstream unbind failed (HTTP {e.status_code}): {upstream_error}. "
                f"Continuing with local cleanup."
            )
        except (PlusNetworkError, PlusRegistrationError, PlusServerError) as e:
            upstream_error = str(e)
            logger.warning(
                f"Upstream unbind unreachable: {upstream_error}. "
                f"Continuing with local cleanup."
            )

        # UNCONDITIONALLY clear local license state (authoritative)
        # This is the key idempotency rule - always clear regardless of upstream result
        if has_license:
            logger.info(f"Clearing local license state for install_id={install_id}")
            instance.signed_license = None
            instance.license_validated_at = None
            self.db.commit()
            self.db.refresh(instance)

            # Invalidate cache
            cache = get_license_cache()
            cache.invalidate(install_id)
            logger.info(f"Local license state cleared for install_id={install_id}")
        else:
            logger.info(f"No local license to clear for install_id={install_id} (already unbound)")

        return {
            "status": "ok",
            "error_message": upstream_error if upstream_error else None,
            "upstream_status": upstream_status
        }
