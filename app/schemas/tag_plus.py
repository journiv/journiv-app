"""
Tag schemas for backend-only features.

NOTE: Plus features now use the bridge pattern and no longer use these schemas.
MonthlyUsageData is kept for the non-Plus get_tag_statistics() method.
"""
from pydantic import BaseModel


class MonthlyUsageData(BaseModel):
    """
    Monthly usage aggregation from database.

    Used by get_tag_statistics() (non-Plus feature) for usage over time data.
    """
    month_key: str  # Format: "YYYY-MM"
    count: int
