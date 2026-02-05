"""
Date and time utilities for import/export operations.

Handles timezone conversion, parsing, and formatting of dates.
"""
from datetime import datetime, timezone
from typing import Optional, Union

from dateutil import parser as date_parser


def parse_datetime(date_str: Union[str, datetime, int, float]) -> datetime:
    """
    Parse a datetime string or object into a datetime.

    Accepts:
    - ISO 8601 strings (with or without timezone)
    - datetime objects
    - Unix timestamps (as int, float, or strings)

    Args:
        date_str: Date string, datetime object, or unix timestamp (int/float)

    Returns:
        Parsed datetime object

    Raises:
        ValueError: If the date string cannot be parsed
        TypeError: If the input type is unsupported
    """
    if isinstance(date_str, datetime):
        return date_str
    elif isinstance(date_str, (int, float)):
        # Unix timestamp
        return datetime.fromtimestamp(date_str, tz=timezone.utc)
    elif isinstance(date_str, str):
        # Try parsing as unix timestamp first
        try:
            timestamp = float(date_str)
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (ValueError, OSError):
            pass

        # Parse as date string
        try:
            dt = date_parser.parse(date_str)
            return dt
        except (ValueError, TypeError) as e:
            raise ValueError(f"Unable to parse date: {date_str}") from e
    else:
        # Defensive check for unexpected types (e.g., None, list, dict, etc.)
        raise TypeError(f"Unsupported date type: {type(date_str)}")


def ensure_utc(dt: datetime) -> datetime:
    """
    Ensure a datetime is in UTC timezone.

    Args:
        dt: Datetime object (may be naive or timezone-aware)

    Returns:
        Datetime in UTC timezone
    """
    if dt.tzinfo is None:
        # Naive datetime - assume it's already UTC
        return dt.replace(tzinfo=timezone.utc)

    # Convert to UTC
    return dt.astimezone(timezone.utc)


def format_datetime(dt: datetime, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Format a datetime object to string.

    Args:
        dt: Datetime object to format
        format_str: strftime format string

    Returns:
        Formatted datetime string
    """
    return dt.strftime(format_str)


def normalize_datetime(date_input: Union[str, datetime, int, float]) -> datetime:
    """
    Parse and normalize a datetime to UTC.

    Combines parse_datetime and ensure_utc for convenience.

    Args:
        date_input: Date string, datetime object, or unix timestamp

    Returns:
        Datetime in UTC timezone

    Raises:
        ValueError: If the date cannot be parsed
    """
    dt = parse_datetime(date_input)
    return ensure_utc(dt)


def safe_parse_datetime(date_input: Union[str, datetime, int, float, None]) -> Optional[datetime]:
    """
    Safely parse a datetime, returning None if parsing fails.

    Args:
        date_input: Date to parse (or None)

    Returns:
        Parsed datetime in UTC, or None if parsing fails or input is None
    """
    if date_input is None:
        return None

    try:
        return normalize_datetime(date_input)
    except (ValueError, TypeError, OSError):
        return None
