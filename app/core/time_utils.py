"""
Timezone-safe datetime utilities for Journiv.

All timestamps are stored in UTC and converted to user's local timezone for display.
Compatible with both SQLite and PostgreSQL.
"""

from datetime import date, datetime, time, timezone
from typing import Optional, Union
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    """
    Return current UTC datetime with timezone info attached.

    Returns:
        datetime: Current UTC datetime (timezone-aware)

    Example:
        >>> now = utc_now()
        >>> now.tzinfo
        datetime.timezone.utc
    """
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime) -> datetime:
    """
    Convert any datetime to UTC.

    If the datetime is naive (no timezone info), it's assumed to be UTC.
    If it has timezone info, it's converted to UTC.

    Args:
        dt: Input datetime (naive or timezone-aware)

    Returns:
        datetime: UTC datetime (timezone-aware)

    Example:
        >>> naive_dt = datetime(2024, 1, 1, 12, 0, 0)
        >>> utc_dt = ensure_utc(naive_dt)
        >>> utc_dt.tzinfo
        datetime.timezone.utc
    """
    if dt.tzinfo is None:
        # Naive datetime - assume UTC
        return dt.replace(tzinfo=timezone.utc)
    else:
        # Convert to UTC
        return dt.astimezone(timezone.utc)


def to_local(dt: datetime, tz_name: Optional[str] = None) -> datetime:
    """
    Convert UTC datetime to user's local timezone.

    Args:
        dt: UTC datetime
        tz_name: IANA timezone name (e.g., "America/Los_Angeles").
                 Defaults to "UTC" if None.

    Returns:
        datetime: Datetime in user's local timezone

    Example:
        >>> utc_dt = datetime(2024, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
        >>> local_dt = to_local(utc_dt, "America/Los_Angeles")
        >>> local_dt.hour
        0
    """
    if tz_name is None:
        tz_name = "UTC"

    # Ensure input is UTC
    utc_dt = ensure_utc(dt)

    # Convert to target timezone
    target_tz = ZoneInfo(tz_name)
    return utc_dt.astimezone(target_tz)


def to_utc(dt: datetime, tz_name: Optional[str] = None) -> datetime:
    """
    Convert local datetime to UTC.

    Args:
        dt: Local datetime (can be naive or timezone-aware)
        tz_name: IANA timezone name. If None and dt is naive, assumes UTC.

    Returns:
        datetime: UTC datetime (timezone-aware)

    Example:
        >>> local_dt = datetime(2024, 1, 1, 0, 0, 0)
        >>> utc_dt = to_utc(local_dt, "America/Los_Angeles")
        >>> utc_dt.hour
        8
    """
    if dt.tzinfo is None and tz_name:
        # Naive datetime - attach timezone
        local_tz = ZoneInfo(tz_name)
        dt = dt.replace(tzinfo=local_tz)

    return ensure_utc(dt)


def local_date_for_user(dt: datetime, tz_name: Optional[str] = None) -> date:
    """
    Extract the local date for a user from a UTC datetime.

    This is critical for entry_date calculation - the same UTC moment
    represents different calendar dates in different timezones.

    Args:
        dt: UTC datetime
        tz_name: User's IANA timezone. Defaults to "UTC" if None.

    Returns:
        date: The local date in the user's timezone

    Example:
        >>> # 11 PM PST on Dec 31 is 7 AM UTC on Jan 1
        >>> utc_dt = datetime(2024, 1, 1, 7, 0, 0, tzinfo=timezone.utc)
        >>> local_date_for_user(utc_dt, "America/Los_Angeles")
        datetime.date(2023, 12, 31)
    """
    if tz_name is None:
        tz_name = "UTC"

    local_dt = to_local(dt, tz_name)
    return local_dt.date()


def start_of_local_day(user_date: date, tz_name: str = "UTC") -> datetime:
    """
    Get the UTC datetime representing the start of a user's local day.

    Args:
        user_date: The local date
        tz_name: User's IANA timezone

    Returns:
        datetime: UTC datetime representing midnight in user's timezone

    Example:
        >>> # Midnight PST on Jan 1, 2024
        >>> start = start_of_local_day(date(2024, 1, 1), "America/Los_Angeles")
        >>> start
        datetime.datetime(2024, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
    """
    local_tz = ZoneInfo(tz_name)
    local_midnight = datetime.combine(user_date, time.min)
    local_midnight = local_midnight.replace(tzinfo=local_tz)
    return local_midnight.astimezone(timezone.utc)


def end_of_local_day(user_date: date, tz_name: str = "UTC") -> datetime:
    """
    Get the UTC datetime representing the end of a user's local day.

    Args:
        user_date: The local date
        tz_name: User's IANA timezone

    Returns:
        datetime: UTC datetime representing 23:59:59.999999 in user's timezone

    Example:
        >>> # End of day PST on Jan 1, 2024
        >>> end = end_of_local_day(date(2024, 1, 1), "America/Los_Angeles")
        >>> end.hour  # UTC hour
        7
    """
    local_tz = ZoneInfo(tz_name)
    local_end = datetime.combine(user_date, time.max)
    local_end = local_end.replace(tzinfo=local_tz)
    return local_end.astimezone(timezone.utc)


def serialize_datetime(dt: Optional[datetime]) -> Optional[str]:
    """
    Convert datetime to ISO8601 UTC string with 'Z' suffix.

    Args:
        dt: Datetime to serialize (can be None)

    Returns:
        str: ISO8601 string ending with 'Z', or None if input is None

    Example:
        >>> dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        >>> serialize_datetime(dt)
        '2024-01-01T12:00:00Z'
    """
    if dt is None:
        return None

    utc_dt = ensure_utc(dt)
    # Format as ISO8601 with 'Z' suffix
    iso_string = utc_dt.isoformat()

    # Replace timezone offset with 'Z'
    if iso_string.endswith('+00:00'):
        iso_string = iso_string[:-6] + 'Z'
    elif not iso_string.endswith('Z'):
        # Remove microseconds and add Z
        if '.' in iso_string:
            iso_string = iso_string.split('.')[0] + 'Z'
        else:
            iso_string = iso_string + 'Z'

    return iso_string


def parse_iso_datetime(value: Union[str, datetime]) -> datetime:
    """
    Parse ISO8601 string to UTC datetime.

    Handles both string and datetime inputs. If datetime is passed,
    ensures it's converted to UTC.

    Args:
        value: ISO8601 string or datetime object

    Returns:
        datetime: UTC datetime (timezone-aware)

    Example:
        >>> dt = parse_iso_datetime("2024-01-01T12:00:00Z")
        >>> dt.tzinfo
        datetime.timezone.utc
    """
    if isinstance(value, datetime):
        return ensure_utc(value)

    # Parse ISO8601 string
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return ensure_utc(dt)


def validate_timezone(tz_name: str) -> bool:
    """
    Validate that a timezone string is a valid IANA timezone.

    Args:
        tz_name: IANA timezone string to validate

    Returns:
        bool: True if valid, False otherwise

    Example:
        >>> validate_timezone("America/Los_Angeles")
        True
        >>> validate_timezone("Invalid/Timezone")
        False
    """
    try:
        ZoneInfo(tz_name)
        return True
    except Exception:
        return False


def normalize_timezone(tz_name: Optional[str]) -> str:
    """
    Normalize and validate a timezone string, with fallback to UTC.

    Handles None values, strips whitespace, validates against IANA timezone
    database, and falls back to UTC if invalid.

    Args:
        tz_name: IANA timezone string to normalize (can be None)

    Returns:
        str: Validated IANA timezone string, or "UTC" if invalid/None

    Example:
        >>> normalize_timezone("America/Los_Angeles")
        "America/Los_Angeles"
        >>> normalize_timezone("  America/New_York  ")
        "America/New_York"
        >>> normalize_timezone("Invalid/Timezone")
        "UTC"
        >>> normalize_timezone(None)
        "UTC"
        >>> normalize_timezone("")
        "UTC"
    """
    from app.core.logging_config import log_warning

    normalized = (tz_name or "UTC").strip() or "UTC"
    try:
        ZoneInfo(normalized)
        return normalized
    except Exception:
        if tz_name:  # Only log warning if user actually provided a value
            log_warning(f"Invalid timezone '{normalized}', defaulting to UTC", timezone=normalized)
        return "UTC"
