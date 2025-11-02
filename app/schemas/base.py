"""
Base schemas with common functionality.
"""
from datetime import datetime, timezone
from pydantic import BaseModel, field_serializer


class TimestampMixin(BaseModel):
    """Mixin for models with created_at/updated_at timestamps.

    Ensures datetime fields are always serialized as UTC ISO 8601 with 'Z' suffix.
    """

    @field_serializer('created_at', 'updated_at', check_fields=False)
    def serialize_datetime(self, dt: datetime, _info):
        """Ensure datetime is serialized as UTC ISO 8601 with 'Z' suffix."""
        if dt is None:
            return None
        if dt.tzinfo is None:
            # If naive datetime, assume it's UTC
            dt = dt.replace(tzinfo=timezone.utc)
        # Convert to UTC and format as ISO 8601 with 'Z' suffix
        return dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda dt: (
                dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
                if dt and dt.tzinfo
                else dt.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')
                if dt
                else None
            )
        }
