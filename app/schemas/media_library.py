"""
Media library schemas.

The media library is a flat, paginated view of every completed media item a
user owns, across all moments — the data behind the web client's Media grid.
Each item carries the owning moment's local calendar day so the grid can group
by month in the moment's own timezone.
"""
import uuid
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel

from app.models.enums import MediaType, UploadStatus


class MediaLibraryItem(BaseModel):
    id: uuid.UUID
    moment_id: uuid.UUID
    media_type: MediaType
    mime_type: str
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None
    alt_text: Optional[str] = None
    upload_status: UploadStatus
    signed_url: Optional[str] = None
    signed_thumbnail_url: Optional[str] = None
    signed_url_expires_at: Optional[int] = None
    signed_thumbnail_expires_at: Optional[int] = None
    created_at: datetime
    # The owning moment's timing, so the grid groups by the moment's own day.
    logged_date_tz: date
    logged_at_utc: datetime
    logged_timezone: str


class MediaLibraryPageResponse(BaseModel):
    items: List[MediaLibraryItem]
    next_cursor_logged_at_utc: Optional[datetime] = None
    next_cursor_id: Optional[uuid.UUID] = None
