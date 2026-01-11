"""
Weather schemas for weather data fetching.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class WeatherFetchRequest(BaseModel):
    """Request schema for weather data fetch."""
    latitude: float = Field(..., ge=-90, le=90, description="Latitude coordinate")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude coordinate")
    entry_datetime_utc: Optional[datetime] = Field(
        None,
        description="Entry timestamp in UTC (ISO format). If provided, weather is fetched for this time.",
    )
    entry_timezone: Optional[str] = Field(
        None,
        description="IANA timezone for the entry timestamp (e.g., America/Los_Angeles).",
    )


class WeatherData(BaseModel):
    """Weather data response."""
    temp_c: float = Field(..., description="Temperature in Celsius")
    temp_f: float = Field(..., description="Temperature in Fahrenheit")
    condition: str = Field(..., description="Weather condition (e.g., Clear, Cloudy, Rain)")
    description: Optional[str] = Field(None, description="Detailed weather description")
    humidity: Optional[int] = Field(None, ge=0, le=100, description="Humidity percentage")
    wind_speed: Optional[float] = Field(None, ge=0, description="Wind speed in m/s")
    pressure: Optional[int] = Field(None, description="Atmospheric pressure in hPa")
    visibility: Optional[int] = Field(None, description="Visibility in meters")
    icon: Optional[str] = Field(None, description="Weather icon code")
    observed_at_utc: Optional[datetime] = Field(
        None,
        description="Authoritative timestamp for the weather observation (UTC)",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "temp_c": 18.5,
                "temp_f": 65.3,
                "condition": "Clear",
                "description": "clear sky",
                "humidity": 65,
                "wind_speed": 3.5,
                "pressure": 1013,
                "visibility": 10000,
                "icon": "01d",
                "observed_at_utc": "2025-12-05T10:30:00Z",
            }
        }


class WeatherFetchResponse(BaseModel):
    """Response schema for weather fetch."""
    weather: WeatherData
    provider: str = Field(..., description="Weather provider used (openweather, etc.)")
    timestamp: str = Field(..., description="Timestamp when weather was fetched (ISO format)")

    class Config:
        json_schema_extra = {
            "example": {
                "weather": {
                    "temp_c": 18.5,
                    "temp_f": 65.3,
                    "condition": "Clear",
                    "description": "clear sky",
                    "humidity": 65,
                    "wind_speed": 3.5,
                    "pressure": 1013,
                    "visibility": 10000,
                    "icon": "01d",
                    "observed_at_utc": "2025-12-05T10:30:00Z"
                },
                "provider": "openweather",
                "timestamp": "2025-12-05T10:30:00Z"
            }
        }


class WeatherServiceDisabledResponse(BaseModel):
    """Response when weather service is disabled (no API key configured)."""
    enabled: bool = Field(False, description="Weather service availability")
    message: str = Field(..., description="Explanation message")

    class Config:
        json_schema_extra = {
            "example": {
                "enabled": False,
                "message": "Weather service is not configured. Please set OPEN_WEATHER_API_KEY_25 or OPEN_WEATHER_API_KEY_30 in environment variables."
            }
        }
