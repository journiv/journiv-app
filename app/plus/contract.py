"""
Shared contract definitions for Plus bridge.

This module defines the data structures exchanged between the Plus binary
and the host application via the bridge. These TypedDict classes provide
IDE support and type checking while remaining standard dictionaries at runtime.

NOTE: This file should be manually copied to journiv-backend at app/plus/contract.py
to maintain sync between repositories. Any changes to contract types should be made
in the Plus repo first, then copied to backend.

IMPORTANT: We have to keep this file in sync between repos to prevent type mismatches.
"""
from typing import Optional, TypedDict


class TagUsageRecord(TypedDict):
    """
    Standard shape of a Tag for the Bridge.

    Used by: fetch_tags_with_usage()

    This represents a single tag with its usage statistics, pre-aggregated
    by the database layer for efficiency.
    """
    id: str           # UUID as string
    name: str         # Tag display name
    usage_count: int  # Number of times this tag has been used
    created_at: str   # ISO 8601 timestamp of tag creation


class MonthlyUsageRecord(TypedDict):
    """
    Monthly aggregated usage data.

    Used by: fetch_tag_monthly_usage()

    This represents SQL-aggregated monthly tag usage counts.
    The aggregation happens in the database layer for performance.
    """
    month_key: str    # Format: "YYYY-MM" (e.g., "2024-03")
    count: int        # Number of tag uses in that month


class TagUsageTimeframe(TypedDict):
    """
    First and last usage timestamps for a tag.

    Used by: fetch_tag_usage_timeframe()

    This provides the temporal boundaries of when a tag has been used,
    computed via SQL MIN/MAX aggregations for efficiency.
    """
    first_used: Optional[str]  # ISO 8601 timestamp or None if never used
    last_used: Optional[str]   # ISO 8601 timestamp or None if never used


__all__ = [
    "TagUsageRecord",
    "MonthlyUsageRecord",
    "TagUsageTimeframe",
]
