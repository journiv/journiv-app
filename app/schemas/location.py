"""
Location schemas for geocoding and location search.
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class LocationSearchRequest(BaseModel):
    """Request schema for location search."""
    query: str = Field(..., min_length=1, max_length=200, description="Location search query")


class LocationResult(BaseModel):
    """Single location search result."""
    name: str = Field(..., description="Display name of the location")
    latitude: float = Field(..., ge=-90, le=90, description="Latitude coordinate")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude coordinate")
    country: Optional[str] = Field(None, description="Country name")
    admin_area: Optional[str] = Field(None, description="State/Province/Region")
    locality: Optional[str] = Field(None, description="City name")
    timezone: Optional[str] = Field(None, description="IANA timezone identifier")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "San Francisco, California, USA",
                "latitude": 37.7749,
                "longitude": -122.4194,
                "country": "United States",
                "admin_area": "California",
                "locality": "San Francisco",
                "timezone": "America/Los_Angeles"
            }
        }


class LocationSearchResponse(BaseModel):
    """Response schema for location search."""
    results: List[LocationResult] = Field(default_factory=list)
    provider: str = Field(..., description="Location provider used (nominatim, etc.)")

    class Config:
        json_schema_extra = {
            "example": {
                "results": [
                    {
                        "name": "San Francisco, California, USA",
                        "latitude": 37.7749,
                        "longitude": -122.4194,
                        "country": "United States",
                        "admin_area": "California",
                        "locality": "San Francisco"
                    }
                ],
                "provider": "nominatim"
            }
        }


class ReverseGeocodeRequest(BaseModel):
    """Request schema for reverse geocoding (lat/lon to location name)."""
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
