"""
Day One data models.

These models represent the Day One JSON export structure.
Day One export format documentation:
https://dayoneapp.com/guides/tips-and-tutorials/exporting-entries/
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
import math
from pydantic import BaseModel, Field, field_validator, model_validator


class DayOneLocation(BaseModel):
    """
    Day One location metadata.
    """
    latitude: Optional[float] = Field(None, alias="latitude", ge=-90, le=90)
    longitude: Optional[float] = Field(None, alias="longitude", ge=-180, le=180)
    place_name: Optional[str] = Field(None, alias="placeName", max_length=500)
    locality_name: Optional[str] = Field(None, alias="localityName", max_length=200)
    administrative_area: Optional[str] = Field(None, alias="administrativeArea", max_length=200)
    country: Optional[str] = Field(None, alias="country", max_length=100)
    time_zone_name: Optional[str] = Field(None, alias="timeZoneName", max_length=100)
    region: Optional[Dict[str, Any]] = Field(None, alias="region")

    @field_validator("latitude", "longitude")
    @classmethod
    def validate_coordinates(cls, v: Optional[float]) -> Optional[float]:
        """Validate coordinates are finite numbers (range checked by Field constraints)."""
        if v is not None and not math.isfinite(v):
            raise ValueError("Coordinate must be a finite number")
        return v

    class Config:
        populate_by_name = True
        extra = "allow"


class DayOneWeather(BaseModel):
    """
    Day One weather metadata.
    """
    temperature_celsius: Optional[float] = Field(None, alias="temperatureCelsius", ge=-100, le=70)
    conditions_description: Optional[str] = Field(None, alias="conditionsDescription", max_length=200)
    weather_code: Optional[str] = Field(None, alias="weatherCode", max_length=50)
    weather_service_name: Optional[str] = Field(None, alias="weatherServiceName", max_length=100)
    relative_humidity: Optional[int] = Field(None, alias="relativeHumidity", ge=0, le=100)
    visibility_km: Optional[float] = Field(None, alias="visibilityKM", ge=0)
    pressure_mb: Optional[float] = Field(None, alias="pressureMB", ge=0)
    wind_speed_kph: Optional[float] = Field(None, alias="windSpeedKPH", ge=0)
    wind_bearing: Optional[int] = Field(None, alias="windBearing", ge=0, le=359)

    @field_validator("wind_bearing", mode="before")
    @classmethod
    def validate_wind_bearing(cls, v: Optional[int]) -> Optional[int]:
        """Normalize invalid wind bearings from Day One exports."""
        if v is None:
            return None
        if v == 360:
            return 0
        if v < 0 or v > 359:
            return None
        return v

    class Config:
        populate_by_name = True
        extra = "allow"


class DayOnePhoto(BaseModel):
    """
    Day One photo metadata.
    """
    identifier: str = Field(..., alias="identifier", min_length=1, max_length=100)
    md5: Optional[str] = Field(None, alias="md5", min_length=32, max_length=32)
    type: Optional[str] = Field(None, alias="type", max_length=50)
    date: Optional[datetime] = Field(None, alias="date")
    order_in_entry: Optional[int] = Field(None, alias="orderInEntry", ge=0)
    favorite: Optional[bool] = Field(None, alias="favorite")
    width: Optional[int] = Field(None, alias="width", ge=0, le=50000)
    height: Optional[int] = Field(None, alias="height", ge=0, le=50000)
    duration: Optional[float] = Field(None, alias="duration", ge=0)
    camera_make: Optional[str] = Field(None, alias="cameraMake", max_length=100)
    camera_model: Optional[str] = Field(None, alias="cameraModel", max_length=100)
    focal_length: Optional[str] = Field(None, alias="focalLength", max_length=50)
    lens_model: Optional[str] = Field(None, alias="lensModel", max_length=100)
    exposure_time: Optional[str] = Field(None, alias="exposureTime", max_length=50)
    fnumber: Optional[str] = Field(None, alias="fnumber", max_length=50)
    iso: Optional[int] = Field(None, alias="iso", ge=0, le=1000000)

    @field_validator("md5")
    @classmethod
    def validate_md5(cls, v: Optional[str]) -> Optional[str]:
        """Validate MD5 hash format (32 hex chars)."""
        if v is not None and not all(c in '0123456789abcdefABCDEF' for c in v):
            raise ValueError("MD5 must be a valid hex string")
        return v.lower() if v else v

    class Config:
        populate_by_name = True
        extra = "allow"


class DayOneVideo(BaseModel):
    """
    Day One video metadata.
    """
    identifier: str = Field(..., alias="identifier", min_length=1, max_length=100)
    md5: Optional[str] = Field(None, alias="md5", min_length=32, max_length=32)
    type: Optional[str] = Field(None, alias="type", max_length=50)
    date: Optional[datetime] = Field(None, alias="date")
    order_in_entry: Optional[int] = Field(None, alias="orderInEntry", ge=0)
    favorite: Optional[bool] = Field(None, alias="favorite")
    duration: Optional[float] = Field(None, alias="duration", ge=0)
    width: Optional[int] = Field(None, alias="width", ge=0, le=50000)
    height: Optional[int] = Field(None, alias="height", ge=0, le=50000)

    @field_validator("md5")
    @classmethod
    def validate_md5(cls, v: Optional[str]) -> Optional[str]:
        """Validate MD5 hash format (32 hex chars)."""
        if v is not None and not all(c in '0123456789abcdefABCDEF' for c in v):
            raise ValueError("MD5 must be a valid hex string")
        return v.lower() if v else v

    class Config:
        populate_by_name = True
        extra = "allow"


class DayOneEntry(BaseModel):
    """
    Day One journal entry.

    Day One stores entries with rich metadata including:
    - Text content (plain and rich text)
    - Creation and modification timestamps
    - Location data
    - Weather data
    - Photos and videos
    - Tags
    - Starred/favorite status
    """
    uuid: str = Field(..., alias="uuid", min_length=1, max_length=100)
    text: Optional[str] = Field(None, alias="text", max_length=10_000_000)
    rich_text: Optional[str] = Field(None, alias="richText", max_length=10_000_000)
    creation_date: datetime = Field(..., alias="creationDate")
    modified_date: Optional[datetime] = Field(None, alias="modifiedDate")
    creation_device: Optional[str] = Field(None, alias="creationDevice", max_length=200)
    creation_device_type: Optional[str] = Field(None, alias="creationDeviceType", max_length=100)
    creation_os_name: Optional[str] = Field(None, alias="creationOSName", max_length=100)
    creation_os_version: Optional[str] = Field(None, alias="creationOSVersion", max_length=100)
    time_zone: Optional[str] = Field(None, alias="timeZone", max_length=100)
    starred: Optional[bool] = Field(None, alias="starred")
    pinned: Optional[bool] = Field(None, alias="pinned")
    is_pinned: Optional[bool] = Field(None, alias="isPinned")
    location: Optional[DayOneLocation] = Field(None, alias="location")
    weather: Optional[DayOneWeather] = Field(None, alias="weather")
    tags: Optional[List[str]] = Field(default_factory=list, alias="tags")
    photos: Optional[List[DayOnePhoto]] = Field(default_factory=list, alias="photos")
    videos: Optional[List[DayOneVideo]] = Field(default_factory=list, alias="videos")
    duration: Optional[float] = Field(None, alias="duration", ge=0)
    editing_time: Optional[float] = Field(None, alias="editingTime", ge=0)
    is_all_day: Optional[bool] = Field(None, alias="isAllDay")

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Optional[List[str]]) -> List[str]:
        """Validate and sanitize tags."""
        if not v:
            return []
        # Limit to 50 tags, max 100 chars each
        validated = []
        for tag in v[:50]:
            if tag and isinstance(tag, str):
                cleaned = tag.strip()[:100]
                if cleaned:
                    validated.append(cleaned)
        return validated

    class Config:
        populate_by_name = True
        extra = "allow"


class DayOneJournal(BaseModel):
    """
    Day One journal container.

    A Day One export can contain multiple journals.
    Each journal has entries associated with it.
    """
    name: str = Field(..., description="Journal name", min_length=1, max_length=500)
    entries: List[DayOneEntry] = Field(default_factory=list, description="Journal entries")
    export_metadata: Optional[Dict[str, Any]] = Field(default=None, description="Export metadata from Day One")
    export_version: Optional[str] = Field(default=None, description="Export version from Day One", max_length=50)
    source_file: Optional[str] = Field(default=None, description="Source JSON filename", max_length=500)

    @field_validator("entries")
    @classmethod
    def validate_entries_limit(cls, v: List[DayOneEntry]) -> List[DayOneEntry]:
        """Validate entries list isn't excessively large."""
        if len(v) > 100000:
            raise ValueError("Too many entries in journal (max 100,000)")
        return v

    class Config:
        extra = "allow"


class DayOneExport(BaseModel):
    """
    Day One export root structure.

    Day One exports contain:
    - metadata (version info)
    - entries array (all entries)

    Note: Day One Classic exports have a flat "entries" array.
    Day One 2+ can have multiple journals, but exports are per-journal.
    """
    metadata: Optional[Dict[str, Any]] = Field(None, alias="metadata")
    entries: List[DayOneEntry] = Field(default_factory=list, alias="entries")
    version: Optional[str] = Field(None, alias="version")

    class Config:
        populate_by_name = True
        extra = "allow"
