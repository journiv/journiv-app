"""
Public endpoints (unauthenticated).

Serves:
  GET /pub/media/{media_id}
  GET /pub/{identifier}/pdf
"""

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.api.dependencies import get_db
from app.core.exceptions import MediaNotFoundError
from app.core.logging_config import LogCategory
from app.services.media_service import MediaService
from app.services.pdf_service import (
    EntryPDFService,
    PDFEntryNotFoundError,
    build_content_disposition,
)

logger = logging.getLogger(LogCategory.API)

router = APIRouter()


@router.get("/pub/{identifier}/pdf")
async def download_published_entry_pdf(
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


@router.get("/pub/media/{media_id}")
async def get_public_media(
    media_id: uuid.UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    """Serve media for published entries."""
    media_service = MediaService()
    try:
        range_header = request.headers.get("Range")

        file_info = await media_service.get_public_media_file_for_serving(
            media_id=media_id,
            session=db,
            range_header=range_header,
        )

        file_path = file_info["file_path"]
        file_size = file_info["file_size"]
        content_type = file_info["content_type"]
        range_info = file_info.get("range_info")

        if range_info:
            start = range_info["start"]
            end = range_info["end"]
            length = range_info["length"]

            def iterfile():
                with open(file_path, "rb") as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(8192, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk

            return StreamingResponse(
                iterfile(),
                media_type=content_type,
                status_code=206,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(length),
                    "Cache-Control": "public, max-age=31536000",
                },
            )

        def iterfile():
            with open(file_path, "rb") as f:
                yield from f

        return StreamingResponse(
            iterfile(),
            media_type=content_type,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(file_size),
                "Cache-Control": "public, max-age=31536000",
            },
        )

    except MediaNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError:
        total_size = "*"
        try:
            file_info = await media_service.get_public_media_file_for_serving(
                media_id=media_id,
                session=db,
                range_header=None,
            )
            total_size = str(file_info.get("file_size", "*"))
        except MediaNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from None
        except Exception:
            total_size = "*"
        raise HTTPException(
            status_code=416,
            detail="Range not satisfiable",
            headers={"Content-Range": f"bytes */{total_size}"},
        ) from None
    except Exception as e:
        logger.error(f"Error serving public media {media_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to serve media") from None
