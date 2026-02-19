"""
Tag schemas.
"""
import uuid
from datetime import date, datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, validator

from app.schemas.base import TimestampMixin
from app.schemas.media_thumbnail import MomentMediaThumbnail


class TagBase(BaseModel):
    """Base tag schema."""
    name: str


class TagCreate(TagBase):
    """Tag creation schema."""

    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Tag name cannot be empty')
        return v.strip().lower()


class TagUpdate(BaseModel):
    """Tag update schema."""
    name: Optional[str] = None

    @validator('name')
    def validate_name(cls, v):
        if v is None:
            return v
        if not v.strip():
            raise ValueError('Tag name cannot be empty')
        return v.strip().lower()


class TagResponse(TagBase, TimestampMixin):
    """Tag response schema."""
    id: uuid.UUID
    user_id: uuid.UUID
    usage_count: int
    created_at: datetime
    updated_at: datetime


class MomentTagLinkBase(BaseModel):
    """Base moment tag link schema."""
    moment_id: uuid.UUID
    tag_id: uuid.UUID


class MomentTagLinkCreate(MomentTagLinkBase):
    """Moment tag link creation schema."""
    pass


class MomentTagLinkResponse(MomentTagLinkBase, TimestampMixin):
    """Moment tag link response schema."""
    created_at: datetime
    updated_at: datetime


class TaggedMomentSummary(BaseModel):
    """Summary payload for moments returned by tag lookups."""
    id: uuid.UUID
    logged_at_utc: datetime
    logged_date_tz: date
    note: Optional[str] = None
    primary_mood_id: Optional[uuid.UUID] = None
    media_count: int = 0
    media: List[MomentMediaThumbnail] = Field(default_factory=list)


class TagSummary(BaseModel):
    """Shared tag summary model used across statistics, tag lists, and related tags."""
    id: uuid.UUID
    name: str
    usage_count: int


class TagStatisticsResponse(BaseModel):
    """Tag usage statistics response schema."""
    total_tags: int
    used_tags: int
    unused_tags: int
    most_used_tag: Optional[TagSummary]
    average_usage: float
    tag_usage_ranking: List[TagSummary]
    recently_created_tags: List[TagSummary]
    usage_over_time: Optional[Dict[str, int]] = None


class TagAnalyticsResponse(TagStatisticsResponse):
    """Extended tag analytics response schema with required time-series data."""
    usage_over_time: Dict[str, int]
    tag_distribution: Dict[str, int]


class PeakMonth(BaseModel):
    """Peak month information."""
    month: str  # Format: "YYYY-MM"
    count: int


class TagDetailAnalyticsResponse(BaseModel):
    """
    Per-tag analytics response.

    Provides detailed analytics for a specific tag including usage trends,
    peak months, and growth analysis.
    """
    # Tag information
    tag_id: uuid.UUID
    tag_name: str
    usage_count: int

    # Time-series data
    usage_over_time: Dict[str, int]  # month_key -> count

    # Usage timeframe
    first_used: Optional[datetime] = None
    last_used: Optional[datetime] = None

    # Plus-computed insights
    peak_month: Optional[PeakMonth] = None
    trend: str  # "increasing", "decreasing", "stable", "insufficient_data"
    growth_rate: Optional[float] = None  # Percentage growth rate

    # Metadata
    days_analyzed: int
