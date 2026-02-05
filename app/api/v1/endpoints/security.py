"""
CSP (Content Security Policy) reporting endpoint.
Handles CSP violation reports for security monitoring.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.config import settings
from app.core.csp_config import get_csp_config
from app.core.logging_config import log_error

router = APIRouter(prefix="/security", tags=["security"])


class CSPViolationReport(BaseModel):
    """CSP violation report model."""
    blocked_uri: Optional[str] = None
    column_number: Optional[int] = None
    document_uri: Optional[str] = None
    effective_directive: Optional[str] = None
    line_number: Optional[int] = None
    original_policy: Optional[str] = None
    referrer: Optional[str] = None
    source_file: Optional[str] = None
    status_code: Optional[int] = None
    violated_directive: Optional[str] = None


class CSPReport(BaseModel):
    """CSP report wrapper."""
    csp_report: CSPViolationReport


@router.post(
    "/csp-report",
    responses={
        500: {"description": "Failed to process CSP report"},
    }
)
async def report_csp_violation(
    request: Request,
    report: CSPReport
):
    """
    Handle CSP violation reports.

    Receives CSP violation reports from browsers when Content Security Policy violations occur.
    """
    try:
        # Extract client information
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")

        violation_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "client_ip": client_ip,
            "user_agent": user_agent,
            "violation": report.csp_report.model_dump(),
            "request_id": getattr(request.state, "request_id", None),
        }

        # Log as warning for monitoring
        log_error(
            Exception(f"CSP Violation: {report.csp_report.violated_directive} blocked URI: {report.csp_report.blocked_uri}"),
            request_id=getattr(request.state, "request_id", ""),
            user_email="",
            violation=violation_payload,
        )

        # TODO: Implement the following:
        # 1. Store violations in database for analysis
        # 2. Send alerts for critical violations
        # 3. Aggregate violation statistics

        return {"status": "received", "message": "CSP violation report received"}

    except Exception as e:
        log_error(e, request_id="", user_email="")
        raise HTTPException(status_code=500, detail="Failed to process CSP report") from None


@router.get(
    "/csp-status",
    responses={
        200: {"description": "CSP configuration status retrieved"},
    }
)
async def get_csp_status():
    """
    Get CSP configuration status.

    Returns current CSP configuration and monitoring status.
    """
    csp_config = get_csp_config(settings.environment)

    return {
        "csp_enabled": csp_config.is_csp_enabled(),
        "environment": settings.environment,
        "reporting_enabled": csp_config.is_reporting_enabled(),
        "hsts_enabled": csp_config.is_hsts_enabled(),
        "report_uri": csp_config.get_report_uri(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": "CSP is active and monitoring violations" if csp_config.is_csp_enabled() else "CSP is disabled"
    }
