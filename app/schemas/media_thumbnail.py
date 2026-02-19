"""
Shared media thumbnail schemas.
"""
import uuid
from typing import Optional

from pydantic import BaseModel

from app.models.enums import MediaType


class MomentMediaThumbnail(BaseModel):
    id: uuid.UUID
    media_type: MediaType
    signed_thumbnail_url: Optional[str] = None
