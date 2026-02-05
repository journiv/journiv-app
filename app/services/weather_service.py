"""
Weather service for fetching weather data using OpenWeather API.
"""
from datetime import datetime, timezone
from typing import Literal, Optional, Tuple

import httpx

from app.core.config import settings
from app.core.http_client import get_http_client
from app.core.logging_config import log_debug, log_error, log_info, log_warning
from app.core.scoped_cache import ScopedCache
from app.core.time_utils import ensure_utc, utc_now
from app.schemas.weather import WeatherData

# Cache configuration
CACHE_TTL_SECONDS = 30 * 60  # 30 minutes
# Approx 1.1km precision for cache keys (2 decimal places)
CACHE_COORD_PRECISION = 2

WeatherProvider = Literal["openweather-current", "openweather-timemachine"]

class WeatherService:
    """Service for fetching weather data using OpenWeather API."""

    OPENWEATHER_TIMEMACHINE_URL = "https://api.openweathermap.org/data/3.0/onecall/timemachine"
    OPENWEATHER_CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather"
    TIMEOUT = 10.0  # seconds

    _cache: Optional[ScopedCache] = None

    @classmethod
    def _get_cache(cls) -> ScopedCache:
        """Get or create the cache instance."""
        if cls._cache is None:
            cls._cache = ScopedCache(namespace="weather")
        return cls._cache

    @classmethod
    def is_enabled(cls) -> bool:
        """Check if weather service is enabled (API key configured)."""
        return bool(settings.open_weather_api_key_25 or settings.open_weather_api_key_30)

    @classmethod
    def _get_cache_key(
        cls,
        latitude: float,
        longitude: float,
        timestamp_utc: Optional[datetime],
    ) -> Tuple[str, str]:
        """
        Generate cache key components.

        Args:
            latitude: GPS latitude
            longitude: GPS longitude
            timestamp_utc: UTC timestamp. If None, assumes current weather.

        Returns:
            Tuple of (scope_id, cache_type)
        """
        lat_rounded = round(latitude, CACHE_COORD_PRECISION)
        lon_rounded = round(longitude, CACHE_COORD_PRECISION)
        coords = f"{lat_rounded},{lon_rounded}"

        if timestamp_utc is None:
            return (coords, "weather-current")

        timestamp_utc = ensure_utc(timestamp_utc)
        # Bucket by hour for historic data to increase cache hit rate
        bucket = int(timestamp_utc.timestamp()) // 3600 * 3600
        return (f"{coords}@{bucket}", "weather-historic")

    @classmethod
    def _get_from_cache(
        cls,
        latitude: float,
        longitude: float,
        timestamp_utc: Optional[datetime],
    ) -> Optional[WeatherData]:
        """Retrieve weather data from cache."""
        try:
            scope_id, cache_type = cls._get_cache_key(latitude, longitude, timestamp_utc)
            cache = cls._get_cache()
            cached_val = cache.get(scope_id=scope_id, cache_type=cache_type)

            if cached_val:
                log_debug(f"Weather cache hit for {scope_id}")
                # Expecting cached_val to be a dict representation of WeatherData
                return WeatherData.model_validate(cached_val)

            return None
        except Exception as e:
            # Don't let cache errors block the feature
            log_warning(f"Weather cache retrieval failed: {e}")
            return None

    @classmethod
    def _save_to_cache(
        cls,
        latitude: float,
        longitude: float,
        timestamp_utc: Optional[datetime],
        weather_data: WeatherData,
    ) -> None:
        """Save weather data to cache."""
        try:
            scope_id, cache_type = cls._get_cache_key(latitude, longitude, timestamp_utc)
            cache = cls._get_cache()

            # cache.set expects a dict or basic type, assume logic handles serialization
            cache.set(
                scope_id=scope_id,
                cache_type=cache_type,
                value=weather_data.model_dump(mode='json'),
                ttl_seconds=CACHE_TTL_SECONDS
            )
            log_debug(f"Weather cached: {cache_type}:{scope_id}")
        except Exception as e:
            log_warning(f"Weather cache save failed: {e}")

    @classmethod
    async def fetch_weather(
        cls,
        latitude: float,
        longitude: float,
        entry_datetime_utc: Optional[datetime] = None,
    ) -> Tuple[Optional[WeatherData], WeatherProvider]:
        """
        Fetch weather data for specific coordinates and optional time.

        Logic:
        1. Validates coordinates.
        2. Determines if request is for "current" or "historic" weather.
        3. Checks cache.
        4. Calls appropriate OpenWeather API.
        5. Caches and returns result.
        """
        cls._validate_coordinates(latitude, longitude)

        # Determine strict UTC timestamp for entry, if provided
        target_dt = ensure_utc(entry_datetime_utc) if entry_datetime_utc else None

        # Decide strategy: Current vs Historic
        # If no date provided, or date is very close to now/future, use Current API
        use_historic = False
        if target_dt:
            now = utc_now()
            diff = (now - target_dt).total_seconds()
            # If entry is over 1 hour old, treat as historic.
            # This can be reduced if needed in future.
            if diff > 3600:
                use_historic = True

        # Check API Key Availability
        api_key_25 = settings.open_weather_api_key_25
        api_key_30 = settings.open_weather_api_key_30

        if not api_key_25 and not api_key_30:
            raise ValueError("Weather service not configured: No API keys found.")

        provider: WeatherProvider
        effective_dt: Optional[datetime] = target_dt if use_historic else None

        if use_historic and api_key_30:
            provider = "openweather-timemachine"
            api_key = api_key_30
        elif api_key_25:
             # Use current API for non-historic requests, or as fallback when 3.0 key unavailable
            provider = "openweather-current"
            api_key = api_key_25
            effective_dt = None # For current weather, we don't cache by timestamp
        elif api_key_30:
             provider = "openweather-timemachine"
             api_key = api_key_30
             effective_dt = target_dt or utc_now() # Timemachine needs a time
             log_info("Using timemachine API for current weather (only 3.0 key configured)")
        else:
            # This should be unreachable due to the API key check above, but satisfies type checkers
            raise ValueError("Weather service not configured: No valid API key/provider combination found.")

        # Try Cache
        cached = cls._get_from_cache(latitude, longitude, effective_dt)
        if cached:
            return cached, provider

        # Fetch Live
        try:
            if provider == "openweather-timemachine":
                # effective_dt should be set if we got here
                fetch_dt = effective_dt or utc_now()
                data = await cls._fetch_timemachine(latitude, longitude, api_key, fetch_dt)
            else:
                data = await cls._fetch_current_weather(latitude, longitude, api_key)

            if data:
                cls._save_to_cache(latitude, longitude, effective_dt, data)
                return data, provider

            return None, provider

        except httpx.HTTPError as e:
             cls._handle_http_error(e, latitude, longitude)
             raise  # Re-raise after logging

    @staticmethod
    def _validate_coordinates(lat: float, lon: float) -> None:
        if not (-90 <= lat <= 90):
            raise ValueError(f"Invalid latitude: {lat}")
        if not (-180 <= lon <= 180):
            raise ValueError(f"Invalid longitude: {lon}")

    @classmethod
    def _handle_http_error(cls, e: httpx.HTTPError, lat: float, lon: float) -> None:
        """Centralized error logging."""
        if isinstance(e, httpx.HTTPStatusError):
            if e.response.status_code == 401:
                log_error(f"OpenWeather 401 Unauthorized for {lat},{lon}. Check API Key.")
                raise ValueError("Invalid OpenWeather API Key.") from e
            elif e.response.status_code == 429:
                log_error("OpenWeather 429 Rate Limit Exceeded.")

            log_error(f"OpenWeather Request Failed: {e.response.status_code} - {e.response.text}")
        else:
            log_error(f"OpenWeather Connection Error: {e}")

    @classmethod
    async def _fetch_timemachine(
        cls,
        lat: float,
        lon: float,
        api_key: str,
        dt: datetime,
    ) -> Optional[WeatherData]:
        params = {
            "lat": lat,
            "lon": lon,
            "dt": int(dt.timestamp()),
            "appid": api_key,
            "units": "metric",
        }
        client = await get_http_client()
        resp = await client.get(cls.OPENWEATHER_TIMEMACHINE_URL, params=params, timeout=cls.TIMEOUT)
        resp.raise_for_status()
        return cls._parse_timemachine_response(resp.json())

    @classmethod
    async def _fetch_current_weather(
        cls,
        lat: float,
        lon: float,
        api_key: str,
    ) -> Optional[WeatherData]:
        params = {
            "lat": lat,
            "lon": lon,
            "appid": api_key,
            "units": "metric",
        }
        client = await get_http_client()
        resp = await client.get(cls.OPENWEATHER_CURRENT_URL, params=params, timeout=cls.TIMEOUT)
        resp.raise_for_status()
        return cls._parse_current_response(resp.json())

    @staticmethod
    def _parse_timemachine_response(data: dict) -> Optional[WeatherData]:
        try:
            # 3.0 OneCall Timemachine returns 'data' list
            items = data.get("data", [])
            if not items:
                return None

            entry = items[0]
            weather_list = entry.get("weather", [{}])
            weather = weather_list[0] if weather_list else {}

            temp_c = entry.get("temp")
            if temp_c is None:
                return None
            feels_like_c = entry.get("feels_like")

            return WeatherData(
                temp_c=round(temp_c, 1),
                temp_f=round((temp_c * 9/5) + 32, 1),
                feels_like_c=round(feels_like_c, 1) if feels_like_c is not None else None,
                feels_like_f=(
                    round((feels_like_c * 9/5) + 32, 1) if feels_like_c is not None else None
                ),
                condition=weather.get("main", "Unknown"),
                description=weather.get("description"),
                humidity=entry.get("humidity"),
                wind_speed=entry.get("wind_speed"),
                pressure=entry.get("pressure"),
                visibility=entry.get("visibility"),
                icon=weather.get("icon"),
                observed_at_utc=datetime.fromtimestamp(entry.get("dt", 0), tz=timezone.utc),
            )
        except Exception as e:
            log_error(f"Error parsing timemachine response: {e}")
            return None

    @staticmethod
    def _parse_current_response(data: dict) -> Optional[WeatherData]:
        try:
            main = data.get("main", {})
            weather_list = data.get("weather", [{}])
            weather = weather_list[0] if weather_list else {}
            wind = data.get("wind", {})

            temp_c = main.get("temp")
            if temp_c is None:
                return None
            feels_like_c = main.get("feels_like")

            return WeatherData(
                temp_c=round(temp_c, 1),
                temp_f=round((temp_c * 9/5) + 32, 1),
                feels_like_c=round(feels_like_c, 1) if feels_like_c is not None else None,
                feels_like_f=(
                    round((feels_like_c * 9/5) + 32, 1) if feels_like_c is not None else None
                ),
                condition=weather.get("main", "Unknown"),
                description=weather.get("description"),
                humidity=main.get("humidity"),
                wind_speed=wind.get("speed"),
                pressure=main.get("pressure"),
                visibility=data.get("visibility"),
                icon=weather.get("icon"),
                observed_at_utc=datetime.fromtimestamp(data.get("dt", 0), tz=timezone.utc),
            )
        except Exception as e:
            log_error(f"Error parsing current weather response: {e}")
            return None
