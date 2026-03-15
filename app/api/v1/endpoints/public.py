"""
Public endpoints (unauthenticated).

Serves:
  GET /pub/{identifier}/pdf
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.api.dependencies import get_db
from app.core.logging_config import LogCategory
from app.services.pdf_service import (
    EntryPDFService,
    PDFEntryNotFoundError,
    build_content_disposition,
)

logger = logging.getLogger(LogCategory.API)

router = APIRouter()


@router.get("/pub/{identifier}/pdf")
def download_published_entry_pdf(
    identifier: str,
    db: Annotated[Session, Depends(get_db)],
):
    """Download a published entry as PDF."""
    pdf_service = EntryPDFService(db)
    try:
        pdf_stream, filename = pdf_service.generate_published_entry_pdf(
            identifier=identifier
        )
        return StreamingResponse(
            pdf_stream,
            media_type="application/pdf",
            headers={"Content-Disposition": build_content_disposition(filename)},
        )

    except PDFEntryNotFoundError:
        raise HTTPException(
            status_code=404, detail="Entry not found or not published"
        ) from None
    except Exception as e:
        logger.error(f"Error generating PDF for {identifier}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate PDF") from None
