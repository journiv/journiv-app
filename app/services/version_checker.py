"""
Version checking service for Journiv Plus integration.

This service handles:
- Checking for updates from Journiv Plus Server
- Managing instance UUID
- Caching version check results
- Rate limit handling
- Offline support via cached responses
- Per-instance authentication via PlusServerClient
"""
import logging
import random
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlmodel import Session, select

from app.core.config import (
    VERSION_CHECK_ENABLED,
    VERSION_CHECK_INTERVAL_HOURS,
    settings,
)
from app.core.instance import get_install_id, get_or_create_instance, get_system_info
from app.core.logging_config import LogCategory, log_error, log_info, log_warning
from app.core.time_utils import parse_iso_datetime, utc_now
from app.core.version_check_cache import get_version_check_cache
from app.models.instance_detail import InstanceDetail
from app.plus.exceptions import (
    PlusNetworkError,
    PlusRateLimitError,
    PlusRegistrationError,
    PlusServerError,
)
from app.plus.plus_client import PlusServerClient


def format_wait_time(seconds: int) -> str:
    """
    Format wait time in a user-friendly way.

    Args:
        seconds: Number of seconds to wait

    Returns:
        Human-readable string like "1 day(s) and 2 hour(s)" or "3 hour(s) and 15 minute(s)"
    """
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60

    if hours == 0 and minutes == 0:
        minutes = 1

    if hours >= 24:
        days = hours // 24
        remaining_hours = hours % 24
        if remaining_hours > 0:
            return f"{days} day(s) and {remaining_hours} hour(s)"
        else:
            return f"{days} day(s)"
    elif hours > 0:
        if minutes > 0:
            return f"{hours} hour(s) and {minutes} minute(s)"
        else:
            return f"{hours} hour(s)"
    else:
        return f"{minutes} minute(s)"


class VersionChecker:
    """
    Service for checking Journiv version updates from Plus server.

    Handles:
    - install_id management for version tracking
    - Background version checks
    - Rate limit handling (429 responses)
    - Error recovery and graceful degradation
    - Caching for offline access

    IMPORTANT: Uses install_id (hardware-bound UUID) NOT the database id field.
    """

    def __init__(self, db: Session):
        """
        Initialize version checker.

        Args:
            db: Database session for install_id and settings
        """
        self.db = db
        self._install_id: Optional[str] = None
        self._backoff_until: Optional[datetime] = None
        self._cache = get_version_check_cache()

    @property
    def install_id(self) -> str:
        """
        Get or create persistent install_id.

        The install_id uniquely identifies this Journiv installation
        for version checking purposes. It's a hardware-bound deterministic
        UUID stored on the single InstanceDetail row.

        Returns:
            str: install_id (hardware-bound UUID)

        Note:
            Uses install_id field (external API identifier), NOT the database id field.
        """
        if self._install_id:
            return self._install_id

        self._install_id = get_install_id(self.db, create_if_missing=True)
        return self._install_id

    def get_instance_info(self) -> Dict[str, str]:
        """
        Get instance information (version, platform, db_backend).

        Returns a dictionary with the same structure used in version check requests.
        This can be reused for other API calls that need instance information.

        Returns:
            Dict with keys: journiv_version, platform, db_backend
        """
        return get_system_info()

    async def check_for_updates(
        self,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Check for updates from Journiv Plus Server.

        Args:
            force: If True, ignore check interval and force immediate check

        Returns:
            Dict containing version check results:
                - success: Whether check succeeded
                - latest_version: Latest version (if available)
                - update_available: Whether update is available
                - error_message: Error message (if failed)
                - rate_limited: Whether request was rate limited
                - retry_after_seconds: Seconds to wait before retry
        """
        # Check if version checking is enabled
        # Skip this check when force=True (manual check should always work)
        if not force and not VERSION_CHECK_ENABLED:
            log_info("Version checking is disabled (system setting)")
            return {
                "success": False,
                "error_message": "Version checking is disabled in settings",
                "rate_limited": False
            }

        # Check if version checking is enabled by user (DB setting)
        # Skip this check when force=True (manual check should always work)
        if not force:
            instance = self.db.exec(select(InstanceDetail).limit(1)).first()
            if instance and not instance.version_check_enabled:
                log_info("Version checking is disabled by user")
                return {
                    "success": False,
                    "error_message": "Version checking is disabled by user",
                    "rate_limited": False
                }

        # Honor backoff after previous failure to avoid hammering Plus
        if self._backoff_until and utc_now() < self._backoff_until:
            retry_after = int((self._backoff_until - utc_now()).total_seconds())
            log_warning(
                f"Version check backoff active for {retry_after}s after previous failure",
                category=LogCategory.APP
            )
            return {
                "success": False,
                "error_message": "Using cached version info while Plus is unreachable",
                "rate_limited": False,
                "backoff_active": True,
                "retry_after_seconds": retry_after
            }

        # Check if we should skip (recently checked)
        if not force:
            last_check = self._get_last_successful_check()
            if last_check:
                checked_at_str = last_check.get("checked_at")
                if checked_at_str:
                    checked_at_utc = parse_iso_datetime(checked_at_str)
                    time_since_check = utc_now() - checked_at_utc
                    interval = timedelta(hours=VERSION_CHECK_INTERVAL_HOURS)

                    if time_since_check < interval:
                        log_info(
                            f"Skipping version check (last check was "
                            f"{time_since_check.total_seconds() / 3600:.1f} hours ago)"
                        )
                        return last_check

        # Perform version check
        try:
            result = await self._perform_version_check()

            # Save to cache
            self._save_check_metadata(result)

            # Manage backoff
            if result.get("success"):
                self._backoff_until = None
            elif not result.get("rate_limited"):
                jitter_seconds = random.randint(30, 90)
                base_seconds = 180
                self._backoff_until = utc_now() + timedelta(seconds=base_seconds + jitter_seconds)
                result["retry_after_seconds"] = base_seconds + jitter_seconds

            return result

        except Exception as exc:
            log_error(exc, context="version_check")
            error_result = {
                "success": False,
                "error_message": str(exc),
                "rate_limited": False
            }
            self._save_check_metadata(error_result)
            # Apply backoff on unexpected errors
            jitter_seconds = random.randint(30, 90)
            base_seconds = 180
            self._backoff_until = utc_now() + timedelta(seconds=base_seconds + jitter_seconds)
            error_result["retry_after_seconds"] = base_seconds + jitter_seconds
            return error_result

    async def _perform_version_check(self) -> Dict[str, Any]:
        """
        Perform actual HTTP request to Plus server using unified client.

        Returns:
            Dict with check results

        Raises:
            PlusServerError: If request fails
        """
        log_info(f"Checking for updates: {settings.app_version}")

        try:
            # Use unified Plus server client
            client = PlusServerClient(self.db)
            data = await client.check_version()

            # Parse successful response
            logging.getLogger(LogCategory.APP).debug(
                "Version check response from Plus server: %s", data
            )

            # data is VersionInfoResponse model
            result = {
                "success": True,
                "latest_version": data.latest_version,
                "update_available": data.update_available or False,
                "update_url": data.update_url,
                "changelog_url": data.changelog_url,
                "full_response": data.model_dump(),
                "status_code": 200,
                "rate_limited": False
            }

            if result["update_available"]:
                log_info(
                    f"Update available: {settings.app_version} -> "
                    f"{result['latest_version']}"
                )
            else:
                log_info(f"No updates available (current: {settings.app_version})")

            return result

        except PlusRateLimitError as e:
            log_warning(
                f"Version check rate limited. Retry after {e.retry_after} seconds"
            )
            return {
                "success": False,
                "rate_limited": True,
                "retry_after_seconds": e.retry_after,
                "status_code": 429,
                "error_message": f"Rate limited. Please wait {format_wait_time(e.retry_after)}."
            }

        except PlusRegistrationError as e:
            # Registration failed - this is non-fatal for version checks
            # Will retry on next scheduled run
            log_warning(f"Version check failed (registration error): {e}")
            return {
                "success": False,
                "error_message": f"Registration with Plus server failed: {e}",
                "status_code": 503,
                "rate_limited": False
            }

        except PlusNetworkError as e:
            # Network error - retry later
            log_warning(f"Version check failed (network error): {e}")
            return {
                "success": False,
                "error_message": f"Network error: {e}",
                "status_code": 503,
                "rate_limited": False
            }

        except PlusServerError as e:
            # Generic server error
            log_warning(f"Version check failed (server error): {e}")
            return {
                "success": False,
                "error_message": str(e),
                "status_code": 500,
                "rate_limited": False
            }

    def _save_check_metadata(self, result: Dict[str, Any]) -> None:
        """
        Save version check result to cache.

        Args:
            result: Check result dictionary
        """
        instance_info = self.get_instance_info()
        cache_result = {
            "success": result.get("success", False),
            "latest_version": result.get("latest_version"),
            "update_available": result.get("update_available"),
            "update_url": result.get("update_url"),
            "changelog_url": result.get("changelog_url"),
            "error_message": result.get("error_message"),
            "status_code": result.get("status_code"),
            "rate_limited": result.get("rate_limited", False),
            "retry_after_seconds": result.get("retry_after_seconds"),
            "install_id": self.install_id,
            "journiv_version": instance_info["journiv_version"],
            "platform": instance_info["platform"],
            "db_backend": instance_info["db_backend"],
        }

        # Always cache the latest check (any status)
        self._cache.set_latest_all(self.install_id, cache_result)

        # Only cache successful checks separately
        if result.get("success", False):
            self._cache.set_latest_success(self.install_id, cache_result)

    def _get_last_successful_check(self) -> Optional[Dict[str, Any]]:
        """
        Get the most recent successful version check from cache.

        Returns:
            Version check result dict or None if no successful checks
        """
        return self._cache.get_latest_success(self.install_id)

    def get_latest_check(self) -> Optional[Dict[str, Any]]:
        """
        Get the most recent version check from cache (successful or not).

        Returns:
            Version check result dict or None if no checks performed
        """
        return self._cache.get_latest_all(self.install_id)

    def get_version_info(self) -> Dict[str, Any]:
        """
        Get current version information and latest check results.

        Returns cached information from the last check, allowing
        offline access to update status.

        Returns:
            Dict with version information:
                - current_version: Current Journiv version
                - install_id: This instance's install_id (hardware-bound UUID)
                - latest_version: Latest available version (if known)
                - update_available: Whether update is available (if known)
                - last_checked: When last check was performed
                - last_check_success: Whether last check succeeded
                - error_message: Error from last check (if failed)
        """
        latest_check = self.get_latest_check()
        last_success = self._get_last_successful_check()

        info = {
            "current_version": settings.app_version,
            "install_id": self.install_id,
            "latest_version": None,
            "update_available": None,
            "update_url": None,
            "changelog_url": None,
            "last_checked": None,
            "last_check_success": None,
            "error_message": None
        }

        if latest_check and latest_check.get("success"):
            checked_at_str = latest_check.get("checked_at")
            checked_at = parse_iso_datetime(checked_at_str) if checked_at_str else None
            info.update({
                "latest_version": latest_check.get("latest_version"),
                "update_available": latest_check.get("update_available"),
                "update_url": latest_check.get("update_url"),
                "changelog_url": latest_check.get("changelog_url"),
                "last_checked": checked_at,
                "last_check_success": True,
                "error_message": None
            })
        elif last_success:
            checked_at_str = last_success.get("checked_at")
            checked_at = parse_iso_datetime(checked_at_str) if checked_at_str else None
            latest_error = latest_check.get("error_message") if latest_check else "unreachable"
            info.update({
                "latest_version": last_success.get("latest_version"),
                "update_available": last_success.get("update_available"),
                "update_url": last_success.get("update_url"),
                "changelog_url": last_success.get("changelog_url"),
                "last_checked": checked_at,
                "last_check_success": False,
                "error_message": (
                    f"Using cached version info from {checked_at.isoformat() if checked_at else 'unknown'} "
                    f"(last check failed: {latest_error})"
                )
            })
        elif latest_check:
            checked_at_str = latest_check.get("checked_at")
            checked_at = parse_iso_datetime(checked_at_str) if checked_at_str else None
            info.update({
                "last_checked": checked_at,
                "last_check_success": False,
                "error_message": latest_check.get("error_message") or "Version check failed"
            })

        return info

    def get_version_check_enabled(self) -> bool:
        """
        Get whether version checking is enabled.

        Returns the current user-controlled setting for version checking.
        Creates a default instance if it doesn't exist.

        Returns:
            bool: True if version checking is enabled, False otherwise
        """
        instance = get_or_create_instance(self.db, create_if_missing=True)
        if instance.version_check_enabled is None:
            instance.version_check_enabled = True
            self.db.commit()
            self.db.refresh(instance)

        return instance.version_check_enabled

    def update_version_check_enabled(self, enabled: bool) -> bool:
        """
        Update whether version checking is enabled.

        Args:
            enabled: Whether to enable version checking

        Returns:
            bool: The updated enabled status
        """
        instance = get_or_create_instance(self.db, create_if_missing=True)
        instance.version_check_enabled = enabled
        self.db.commit()
        self.db.refresh(instance)

        return instance.version_check_enabled
