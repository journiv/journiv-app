"""
Location endpoints for geocoding and location search.
"""
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies import get_current_user
from app.core.logging_config import log_error
from app.models.user import User
from app.schemas.location import (
    LocationResult,
    LocationSearchRequest,
    LocationSearchResponse,
    ReverseGeocodeRequest,
)
from app.services.location_service import LocationService

router = APIRouter(prefix="/location", tags=["location"])


@router.post(
    "/search",
    response_model=LocationSearchResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Invalid search query"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        500: {"description": "Internal server error"},
        503: {"description": "Location service unavailable"},
    }
)
async def search_location(
    http_request: Request,
    search_request: LocationSearchRequest,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    Search for locations by query string.

    Uses Nominatim (OpenStreetMap) for geocoding.
    Rate limited to respect Nominatim's usage policy.
    """
    # Validate query is not empty after trimming
    query = search_request.query.strip()
    if not query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search query cannot be empty"
        )

    try:
        results = await LocationService.search(query, limit=5)

        return LocationSearchResponse(
            results=results,
            provider="nominatim"
        )

    except httpx.HTTPError as e:
        log_error(
            e,
            request_id=getattr(http_request.state, 'request_id', None),
            user_email=current_user.email,
            query=search_request.query
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Location service temporarily unavailable. Please try again later."
        ) from None
    except Exception as e:
        log_error(
            e,
            request_id=getattr(http_request.state, 'request_id', None),
            user_email=current_user.email,
            query=search_request.query
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while searching for locations"
        ) from None


@router.post(
    "/reverse",
    response_model=LocationResult,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Invalid coordinates"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        404: {"description": "Location not found"},
        500: {"description": "Internal server error"},
        503: {"description": "Location service unavailable"},
    }
)
async def reverse_geocode(
    http_request: Request,
    geocode_request: ReverseGeocodeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    Reverse geocode coordinates to location name.

    Converts latitude/longitude to a human-readable location name.
    """
    try:
        result = await LocationService.reverse_geocode(
            geocode_request.latitude,
            geocode_request.longitude
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No location found for the given coordinates"
            )

        return result

    except HTTPException:
        raise
    except httpx.HTTPError as e:
        log_error(
            e,
            request_id=getattr(http_request.state, 'request_id', None),
            user_email=current_user.email,
            latitude=geocode_request.latitude,
            longitude=geocode_request.longitude
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Location service temporarily unavailable. Please try again later."
        ) from None
    except Exception as e:
        log_error(
            e,
            request_id=getattr(http_request.state, 'request_id', None),
            user_email=current_user.email,
            latitude=geocode_request.latitude,
            longitude=geocode_request.longitude
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while reverse geocoding"
        ) from None
