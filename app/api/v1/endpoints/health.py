"""
Simple health check endpoint.
"""
import os
from datetime import datetime, timezone
from typing import Annotated, Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import literal
from sqlmodel import Session, select

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from app.core.config import settings
from app.core.database import get_session
from app.core.logging_config import log_error

router = APIRouter(tags=["health"])


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get(
    "/health",
    response_model=Dict[str, Any],
    responses={
        500: {"description": "Internal server error"},
    }
)
async def health_check(session: Annotated[Session, Depends(get_session)]):
    """
    Detailed health check with database status.

    Returns degraded status if database is unreachable but service is running.
    """
    try:
        # Check database connection
        db_status = "connected"
        try:
            session.exec(select(literal(1))).first()
        except Exception as e:
            db_status = f"disconnected: {str(e)}"

        return {
            "status": "healthy" if db_status == "connected" else "degraded",
            "timestamp": _utc_now_iso(),
            "service": settings.app_name,
            "version": settings.app_version,
            "database": db_status
        }
    except Exception as e:
        log_error(e, request_id=None)
        raise HTTPException(status_code=500, detail="Health check failed") from None


@router.get(
    "/memory",
    response_model=Dict[str, Any],
    responses={
        500: {"description": "Internal server error"},
    }
)
async def memory_status():
    """
    Get current memory usage status.

    Returns system and process memory metrics for monitoring.
    """
    try:
        if not PSUTIL_AVAILABLE:
            return {
                "status": "unavailable",
                "timestamp": _utc_now_iso(),
                "message": "psutil not available - memory monitoring disabled"
            }

        # Get system memory info
        memory = psutil.virtual_memory()

        # Get current process memory info
        process = psutil.Process(os.getpid())
        process_memory = process.memory_info()

        # Calculate memory usage percentage
        memory_percent = memory.percent
        process_memory_mb = process_memory.rss / 1024 / 1024

        # Determine status based on usage
        if memory_percent > 90:
            status = "critical"
        elif memory_percent > 80:
            status = "warning"
        else:
            status = "ok"

        return {
            "status": status,
            "timestamp": _utc_now_iso(),
            "system_memory": {
                "total_mb": round(memory.total / 1024 / 1024, 1),
                "used_mb": round(memory.used / 1024 / 1024, 1),
                "available_mb": round(memory.available / 1024 / 1024, 1),
                "percent_used": round(memory_percent, 1)
            },
            "process_memory": {
                "rss_mb": round(process_memory_mb, 1),
                "vms_mb": round(process_memory.vms / 1024 / 1024, 1)
            }
        }
    except Exception as e:
        log_error(e, request_id=None)
        raise HTTPException(status_code=500, detail="Failed to get memory status") from None
