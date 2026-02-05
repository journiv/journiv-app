"""
Plus-scoped tag schemas for backend-to-plus communication.
"""
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class TagRawData(BaseModel):
    """Raw tag data."""
    id: uuid.UUID
    name: str
    usage_count: int


class MonthlyUsageData(BaseModel):
    """Monthly usage aggregation from database."""
    month_key: str  # Format: "YYYY-MM"
    count: int


class TagAnalyticsRawData(BaseModel):
    """
    Raw data input for Plus tag analytics computation.
    """
    # Basic counts from database
    total_tags: int
    used_tags: int

    # Raw tag data (already sorted by usage_count desc, name asc)
    all_tags: List[TagRawData]

    # Most used tag (first in ranking, but separated for clarity)
    most_used_tag: TagRawData | None

    # Recently created tags (last 20, sorted by created_at desc)
    recently_created_tags: List[TagRawData]

    # Raw monthly usage data from database (unsorted)
    monthly_usage_raw: List[MonthlyUsageData]

    # Average usage per tag (pre-computed in DB for efficiency)
    average_usage: float


class TagDetailAnalyticsRawData(BaseModel):
    """
    Raw data input for per-tag analytics.

    Contains database query results for a single tag.
    All queries are pre-filtered by user_id and tag_id for privacy.
    """
    # Tag identification
    tag_id: uuid.UUID
    tag_name: str
    total_usage_count: int

    # Monthly usage data (SQL-aggregated)
    monthly_usage: List[MonthlyUsageData]

    # Usage timeframe
    first_used: Optional[datetime] = None
    last_used: Optional[datetime] = None

    # Query parameters (for context)
    days_requested: int
