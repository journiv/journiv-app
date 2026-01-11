"""
Weather endpoints for fetching weather data.
"""
from typing import Annotated
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
import httpx

from app.api.dependencies import get_current_user
from app.core.logging_config import log_error, log_warning, redact_coordinates
from app.core.time_utils import normalize_timezone, to_utc
from app.models.user import User
from app.schemas.weather import (
    WeatherFetchRequest,
    WeatherFetchResponse,
    WeatherServiceDisabledResponse,
)
from app.services.weather_service import WeatherService

router = APIRouter(prefix="/weather", tags=["weather"])


@router.post(
    "/fetch",
    response_model=WeatherFetchResponse | WeatherServiceDisabledResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Invalid coordinates"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        500: {"description": "Internal server error"},
        503: {"description": "Weather service unavailable"},
    }
)
async def fetch_weather(
    http_request: Request,
    weather_request: WeatherFetchRequest,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    Fetch weather data for given coordinates and entry time.

    Uses OpenWeather API. Requires OPEN_WEATHER_API_KEY_25 or OPEN_WEATHER_API_KEY_30 to be configured.
    Returns structured error if weather service is not configured.
    """
    # Check if weather service is enabled
    if not WeatherService.is_enabled():
        return WeatherServiceDisabledResponse(
            enabled=False,
            message="Weather service is not configured. Please set OPEN_WEATHER_API_KEY_25 or OPEN_WEATHER_API_KEY_30 in environment variables of your Journiv backend."
        )

    try:
        entry_timezone = normalize_timezone(weather_request.entry_timezone)
        entry_datetime_utc = None
        if weather_request.entry_datetime_utc is not None:
            entry_datetime_utc = to_utc(weather_request.entry_datetime_utc, entry_timezone)

        weather_data, provider = await WeatherService.fetch_weather(
            weather_request.latitude,
            weather_request.longitude,
            entry_datetime_utc,
        )

        if not weather_data:
            # This happens if parsing fails or data is missing despite success status
            # We treat it as service unavailable or data unavailable
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve weather data from provider."
            )

        return WeatherFetchResponse(
            weather=weather_data,
            provider=provider,
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        )

    except ValueError as e:
        # Service raises ValueError for config issues or invalid coords
        error_message = str(e)
        log_warning(
            f"Weather service error: {error_message}",
            request_id=getattr(http_request.state, 'request_id', None),
            **redact_coordinates(weather_request.latitude, weather_request.longitude) or {}
        )
        return WeatherServiceDisabledResponse(
            enabled=False,
            message=error_message
        )
    except httpx.HTTPStatusError as e:
        # Detailed handling for specific HTTP errors
        if e.response.status_code == 401:
             return WeatherServiceDisabledResponse(
                enabled=False,
                message=(
                    "Invalid OpenWeather API key. Please check your backend configuration."
                )
            )

        log_error(
            e,
            request_id=getattr(http_request.state, 'request_id', None),
            **redact_coordinates(weather_request.latitude, weather_request.longitude) or {}
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Weather service temporarily unavailable."
        )
    except Exception as e:
        log_error(
            e,
            request_id=getattr(http_request.state, 'request_id', None),
            **redact_coordinates(weather_request.latitude, weather_request.longitude) or {}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching weather data"
        )
