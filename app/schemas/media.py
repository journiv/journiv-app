"""
Media and import job schemas.
"""
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, computed_field

from app.models.enums import JobStatus
from app.models.integration import AssetType
from app.schemas.entry import EntryMediaResponse


class ImmichImportJobResponse(BaseModel):
    """Response schema for import job status mapping to unified ImportJob."""
    job_id: uuid.UUID = Field(..., alias="id")
    entry_id: Optional[uuid.UUID] = None
    status: JobStatus
    total_items: int
    processed_items: int
    failed_items: int
    result_data: Optional[Dict[str, Any]] = None
    errors: Optional[list[str]] = None
    warnings: Optional[list[str]] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @computed_field
    def progress_percent(self) -> float:
        """Calculate progress percentage for backward compatibility or UI."""
        if self.total_items == 0:
            return 0.0
        return ((self.processed_items + self.failed_items) / self.total_items) * 100

    class Config:
        from_attributes = True
        populate_by_name = True


class ImmichImportStartResponse(BaseModel):
    """Response when starting an async import job."""
    job_id: uuid.UUID
    status: str = "accepted"
    message: str
    total_assets: int
    media: list[EntryMediaResponse] = Field(default_factory=list)


class ImmichImportAsset(BaseModel):
    """Optional Immich asset metadata to seed placeholder media."""
    id: str
    type: Optional[AssetType] = None
    title: Optional[str] = None
    taken_at: Optional[datetime] = None
    thumb_url: Optional[str] = None
    original_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class MediaSignedUrlResponse(BaseModel):
    """Response schema for short-lived signed media URLs."""
    signed_url: str
    expires_at: int


class MediaBatchSignItem(BaseModel):
    """Single batch signing request item."""
    id: str
    variant: str


class MediaBatchSignRequest(BaseModel):
    """Batch signing request payload."""
    items: list[MediaBatchSignItem] = Field(..., min_length=1, max_length=100)


class MediaBatchSignResult(BaseModel):
    """Batch signing result for a single item."""
    id: str
    variant: str
    signed_url: str
    expires_at: int


class MediaBatchSignError(BaseModel):
    """Batch signing error for a single item."""
    id: str
    variant: str
    error: str


class MediaBatchSignResponse(BaseModel):
    """Batch signing response payload."""
    results: list[MediaBatchSignResult] = Field(default_factory=list)
    errors: list[MediaBatchSignError] = Field(default_factory=list)


class ImmichImportRequest(BaseModel):
    """Request to import assets from Immich."""
    asset_ids: list[str] = Field(..., min_length=1, max_length=100)
    entry_id: uuid.UUID
    assets: Optional[list[ImmichImportAsset]] = None
