"""
Instance and Install ID Management.

This module consolidates logic for:
- Managing the singleton InstanceDetail record
- System information gathering (platform, version)
- Deterministic install_id generation (CRC32 + UUIDv5)
"""
import logging
import os
from typing import Dict

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.core.config import settings
from app.core.install_id import generate_install_id
from app.core.logging_config import LogCategory, log_info
from app.models.instance_detail import InstanceDetail

logger = logging.getLogger(LogCategory.APP)


# =============================================================================
# Instance Management (Database)
# =============================================================================

def get_or_create_instance(db: Session, create_if_missing: bool = True, _retry_count: int = 0) -> InstanceDetail:
    """
    Get or create the singleton InstanceDetail record.

    Args:
        db: Database session
        create_if_missing: If True, creates InstanceDetail if missing.
        _retry_count: Internal retry counter to prevent infinite recursion.

    Returns:
        InstanceDetail: The singleton instance record

    Raises:
        RuntimeError: If create_if_missing=False and instance doesn't exist
    """
    rows = list(db.exec(select(InstanceDetail).order_by(col(InstanceDetail.id))).all())

    if len(rows) == 0:
        instance = None
    elif len(rows) == 1:
        instance = rows[0]
    else:
        logger.error(
            f"Multiple InstanceDetail records found ({len(rows)} records). "
            "This violates the singleton constraint. Record IDs: "
            f"{[r.id for r in rows]}"
        )
        raise RuntimeError(
            f"Multiple InstanceDetail singleton records detected ({len(rows)} records). "
            "Database integrity violation."
        )

    if instance:
        # If instance exists but has no install_id (legacy/migration case), populate it
        if not instance.install_id:
            instance.install_id = generate_install_id()
            db.add(instance)
            try:
                db.commit()
                db.refresh(instance)
            except Exception as e:
                db.rollback()
                raise RuntimeError(f"Failed to update install_id: {e}") from e
        return instance

    if not create_if_missing:
        raise RuntimeError("InstanceDetail with install_id must be initialized at startup")

    # Create new instance with auto-generated install_id
    new_instance = InstanceDetail(install_id=generate_install_id(), singleton_marker=1)
    db.add(new_instance)

    try:
        db.commit()
        db.refresh(new_instance)
    except IntegrityError:
        # Another process created the instance concurrently
        db.rollback()
        if _retry_count >= 3:
            raise RuntimeError("Failed to create instance after multiple retries due to IntegrityError") from None
        logger.warning("Concurrent instance creation detected, retrying fetch")
        return get_or_create_instance(db, create_if_missing=True, _retry_count=_retry_count + 1)
    except Exception as e:
        db.rollback()
        raise RuntimeError(f"Failed to create instance: {e}") from e

    log_info(
        f"Generated new install_id: {new_instance.install_id}",
        category=LogCategory.APP
    )
    return new_instance


def get_instance_strict(db: Session) -> InstanceDetail:
    """
    Get the singleton InstanceDetail record, raising if missing or invalid.

    Use when the instance is guaranteed to exist (e.g., after startup).
    """
    rows = list(db.exec(
        select(InstanceDetail)
        .where(col(InstanceDetail.install_id).is_not(None))
        .order_by(col(InstanceDetail.id))
    ).all())

    if len(rows) == 0:
        raise RuntimeError("InstanceDetail with install_id must be initialized at startup")
    elif len(rows) == 1:
        instance = rows[0]
    else:
        logger.error(
            f"Multiple InstanceDetail records found ({len(rows)} records). "
            "This violates the singleton constraint. Record IDs: "
            f"{[r.id for r in rows]}"
        )
        raise RuntimeError(
            f"Multiple InstanceDetail singleton records detected ({len(rows)} records). "
            "Database integrity violation."
        )

    return instance


def get_install_id(db: Session, create_if_missing: bool = True) -> str:
    """
    Get the install_id string from the singleton InstanceDetail.

    Convenience wrapper around get_or_create_instance.
    """
    instance = get_or_create_instance(db, create_if_missing=create_if_missing)
    return instance.install_id


# =============================================================================
# System Information
# =============================================================================

def detect_platform() -> str:
    """Detect if running in container or bare metal installation."""
    # Check Podman marker
    if os.path.exists("/run/.containerenv"):
        return "container"

    # Check Docker marker
    if os.path.exists("/.dockerenv"):
        return "container"

    # Check cgroup for container patterns (Docker, Kubernetes, LXC, containerd)
    try:
        with open("/proc/1/cgroup", "r", encoding="utf-8") as f:
            content = f.read()
            if any(pattern in content for pattern in ["docker", "kubepods", "lxc", "containerd"]):
                return "container"
    except (FileNotFoundError, PermissionError, OSError):
        pass

    # Check container environment variable
    if os.getenv("container"):
        return "container"

    # Default to bare metal installation
    return "bare-metal"


def get_db_backend() -> str:
    """Get database backend type."""
    return settings.database_type


def get_system_info() -> Dict[str, str]:
    """Get standard system information."""
    return {
        "journiv_version": settings.app_version,
        "platform": detect_platform(),
        "db_backend": get_db_backend()
    }
