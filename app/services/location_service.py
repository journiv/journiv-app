"""
Location service for geocoding and location search using Nominatim (OpenStreetMap).
"""
import asyncio
import time
from typing import Any, List, Optional

import httpx

from app.core.http_client import get_http_client
from app.core.logging_config import log_debug, log_error, log_info, log_warning
from app.core.scoped_cache import ScopedCache
from app.schemas.location import LocationResult

# Cache configuration
CACHE_TTL_SECONDS = 24 * 3600  # 24 hours

# Sentinel to distinguish cache miss from cached None
_CACHE_MISS = object()


class LocationService:
    """Service for location search and geocoding using Nominatim."""

    NOMINATIM_URL = "https://nominatim.openstreetmap.org"
    USER_AGENT = "Journiv/1.0 (Self-hosted journaling app; https://www.journiv.com)"
    TIMEOUT = 10.0  # seconds
    RATE_LIMIT_DELAY = 1.0  # Nominatim requires 1 request per second max
    MAX_CACHE_RESULTS = 10

    _cache: Optional[ScopedCache] = None

    _last_request_time: Optional[float] = None
    _rate_limit_lock: Optional[asyncio.Lock] = None

    @classmethod
    def _get_cache(cls) -> ScopedCache:
        """Get or create the cache instance."""
        if cls._cache is None:
            cls._cache = ScopedCache(namespace="location")
        return cls._cache

    @classmethod
    def _get_cache_key(cls, query_type: str, *args) -> tuple[str, str]:
        """
        Generate cache key components for ScopedCache.

        Returns:
            Tuple of (scope_id, cache_type) for use with ScopedCache
        """
        if query_type == "search":
            query = str(args[0]).lower().strip()
            # Use query as scope_id, "search" as cache_type
            # Replace colons to prevent conflicts with key format
            safe_query = query.replace(":", "_")
            return (safe_query, "search")
        elif query_type == "reverse":
            lat, lon = args
            # Round to 3 decimal places (~111m precision) for better caching
            coords = f"{round(lat, 3)},{round(lon, 3)}"
            return (coords, "reverse")
        # Fallback for other query types
        safe_args = "_".join(str(arg).replace(":", "_") for arg in args)
        return (safe_args, query_type)

    @classmethod
    def _get_from_cache(cls, query_type: str, *args) -> Optional[Any]:
        """Get location data from cache if available."""
        try:
            scope_id, cache_type = cls._get_cache_key(query_type, *args)
            cache = cls._get_cache()
            cached_data = cache.get(scope_id=scope_id, cache_type=cache_type)

            if cached_data is not None:
                log_debug(f"Location cache hit for {cache_type}:{scope_id}")
                # Extract and deserialize the result
                result_data = cached_data.get("result", _CACHE_MISS)

                if result_data is _CACHE_MISS:
                    return _CACHE_MISS

                # Deserialize based on query type
                if query_type == "search":
                    # List of LocationResult objects
                    return [LocationResult(**item) for item in result_data]
                elif query_type == "reverse":
                    # Single LocationResult object or None
                    return LocationResult(**result_data) if result_data is not None else None

                return result_data

            return _CACHE_MISS
        except Exception as e:
            log_warning(f"Failed to get from cache: {e}")
            return _CACHE_MISS

    @classmethod
    def _save_to_cache(cls, query_type: str, result: Any, *args) -> None:
        """Save location data to cache with TTL."""
        try:
            scope_id, cache_type = cls._get_cache_key(query_type, *args)
            cache = cls._get_cache()

            # Serialize Pydantic models to dict for JSON storage
            if query_type == "search" and result is not None:
                # List of LocationResult objects
                serialized_result = [item.model_dump() for item in result]
            elif query_type == "reverse" and result is not None:
                # Single LocationResult object
                serialized_result = result.model_dump()
            else:
                # None or other types
                serialized_result = result

            # Wrap result in a dict for consistency
            cache_data = {"result": serialized_result}
            cache.set(
                scope_id=scope_id,
                cache_type=cache_type,
                value=cache_data,
                ttl_seconds=CACHE_TTL_SECONDS
            )
            log_debug(f"Location cached: {cache_type}:{scope_id}")
        except Exception as e:
            log_warning(f"Failed to save to cache: {e}")

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        """Get or create the rate limit lock."""
        if cls._rate_limit_lock is None:
            cls._rate_limit_lock = asyncio.Lock()
        return cls._rate_limit_lock

    @classmethod
    async def _respect_rate_limit(cls):
        """Ensure we don't exceed Nominatim's rate limit (1 req/sec)."""
        lock = cls._get_lock()
        async with lock:
            if cls._last_request_time is not None:
                elapsed = time.monotonic() - cls._last_request_time
                if elapsed < cls.RATE_LIMIT_DELAY:
                    sleep_time = cls.RATE_LIMIT_DELAY - elapsed
                    log_debug(f"Rate limiting: sleeping for {sleep_time:.2f}s")
                    await asyncio.sleep(sleep_time)
            cls._last_request_time = time.monotonic()

    @classmethod
    async def search(cls, query: str, limit: int = 5) -> List[LocationResult]:
        """
        Search for locations by query string.

        Uses 24-hour caching to reduce API calls and respect Nominatim usage policy.

        Args:
            query: Location search query (e.g., "San Francisco")
            limit: Maximum number of results to return (1-10)

        Returns:
            List of LocationResult objects

        Raises:
            ValueError: If query is invalid
            httpx.HTTPError: If the request fails
        """
        # Validate input
        if not query or not query.strip():
            raise ValueError("Search query cannot be empty")

        query = query.strip()
        if len(query) > 200:
            raise ValueError("Search query too long (max 200 characters)")

        limit = max(1, min(limit, 10))

        # Check cache first
        cached_result = cls._get_from_cache("search", query)
        if cached_result is not _CACHE_MISS:
            if cached_result is None:
                return []
            return cached_result[:limit]

        await cls._respect_rate_limit()

        params = {
            "q": query,
            "format": "json",
            "addressdetails": 1,
            "limit": cls.MAX_CACHE_RESULTS,
            "accept-language": "en",
        }

        headers = {
            "User-Agent": cls.USER_AGENT,
        }

        try:
            client = await get_http_client()
            response = await client.get(
                f"{cls.NOMINATIM_URL}/search",
                params=params,
                headers=headers,
                timeout=cls.TIMEOUT,
            )
            if response.status_code == 429:
                log_warning(f"Nominatim rate limit exceeded for '{query}'")
                raise httpx.HTTPStatusError(
                    "Rate limit exceeded",
                    request=response.request,
                    response=response
                )

            response.raise_for_status()
            data = response.json()

            # Handle empty or invalid responses
            if not isinstance(data, list):
                log_warning(f"Nominatim returned non-list response for '{query}': {type(data)}")
                return []

            results = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                result = cls._parse_nominatim_result(item)
                if result:
                    results.append(result)

            # Save to cache (up to MAX_CACHE_RESULTS)
            cls._save_to_cache("search", results[:cls.MAX_CACHE_RESULTS], query)

            log_info(f"Location search for '{query}' returned {len(results)} results")
            return results[:limit]

        except httpx.TimeoutException as e:
            log_error(
                e,
                query=query
            )
            raise httpx.HTTPError(f"Request timeout: {e}") from e
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                log_error(
                    e,
                    query=query
                )
                raise httpx.HTTPError("Rate limit exceeded. Please try again later.") from e

            log_error(
                e,
                query=query,
                status_code=e.response.status_code
            )
            raise
        except httpx.HTTPError as e:
            log_error(
                e,
                query=query
            )
            raise

    @classmethod
    async def reverse_geocode(cls, latitude: float, longitude: float) -> Optional[LocationResult]:
        """
        Reverse geocode coordinates to location name.

        Uses 24-hour caching to reduce API calls and respect Nominatim usage policy.

        Args:
            latitude: Latitude coordinate (-90 to 90)
            longitude: Longitude coordinate (-180 to 180)

        Returns:
            LocationResult if successful, None if location not found

        Raises:
            ValueError: If coordinates are invalid
            httpx.HTTPError: If the request fails (network error, timeout, etc.)
        """
        # Validate coordinates
        if not (-90 <= latitude <= 90):
            raise ValueError(f"Invalid latitude: {latitude} (must be -90 to 90)")
        if not (-180 <= longitude <= 180):
            raise ValueError(f"Invalid longitude: {longitude} (must be -180 to 180)")

        # Check cache first
        cached_result = cls._get_from_cache("reverse", latitude, longitude)
        if cached_result is not _CACHE_MISS:
            return cached_result

        await cls._respect_rate_limit()

        params = {
            "lat": latitude,
            "lon": longitude,
            "format": "json",
            "addressdetails": 1,
            "accept-language": "en",
        }

        headers = {
            "User-Agent": cls.USER_AGENT,
        }

        try:
            client = await get_http_client()
            response = await client.get(
                f"{cls.NOMINATIM_URL}/reverse",
                params=params,
                headers=headers,
                timeout=cls.TIMEOUT,
            )

            if response.status_code == 429:
                log_warning(f"Nominatim rate limit exceeded for reverse geocode ({latitude}, {longitude})")
                raise httpx.HTTPStatusError(
                    "Rate limit exceeded",
                    request=response.request,
                    response=response
                )

            response.raise_for_status()
            data = response.json()

            # Check if Nominatim returned an error response
            if isinstance(data, dict) and data.get("error"):
                log_warning(
                    f"Nominatim returned error for ({latitude}, {longitude}): {data.get('error')}",
                    latitude=latitude,
                    longitude=longitude
                )
                return None

            result = cls._parse_nominatim_result(data)
            if result:
                # Save to cache
                cls._save_to_cache("reverse", result, latitude, longitude)
                log_info(f"Reverse geocode for ({latitude}, {longitude}) successful")
            else:
                # Cache negative results too (with same TTL)
                cls._save_to_cache("reverse", None, latitude, longitude)
            return result

        except httpx.TimeoutException as e:
            log_error(
                e,
                latitude=latitude,
                longitude=longitude
            )
            raise httpx.HTTPError(f"Request timeout: {e}") from e
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                log_error(
                    e,
                    latitude=latitude,
                    longitude=longitude
                )
                raise httpx.HTTPError("Rate limit exceeded. Please try again later.") from e

            log_error(
                e,
                latitude=latitude,
                longitude=longitude,
                status_code=e.response.status_code
            )
            raise
        except httpx.HTTPError as e:
            log_error(
                e,
                latitude=latitude,
                longitude=longitude
            )
            raise

    @classmethod
    def _parse_nominatim_result(cls, item: dict) -> Optional[LocationResult]:
        """Parse Nominatim API response into LocationResult."""
        try:
            address = item.get("address", {})

            # Build display name
            display_name = item.get("display_name", "")

            # Extract structured components
            country = address.get("country")
            admin_area = (
                address.get("state")
                or address.get("province")
                or address.get("region")
            )
            locality = (
                address.get("city")
                or address.get("town")
                or address.get("village")
                or address.get("hamlet")
            )

            return LocationResult(
                name=display_name,
                latitude=float(item["lat"]),
                longitude=float(item["lon"]),
                country=country,
                admin_area=admin_area,
                locality=locality,
                timezone=None,  # Nominatim doesn't provide timezone
            )

        except (KeyError, ValueError, TypeError) as e:
            log_warning(f"Failed to parse Nominatim result: {e}")
            return None
