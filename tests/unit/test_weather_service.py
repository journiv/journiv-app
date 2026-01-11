import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
import httpx

from app.services.weather_service import WeatherService, WeatherData
from app.core.config import settings

# Sample Data
SAMPLE_MSG_CURRENT = {
    "weather": [{"main": "Clear", "description": "clear sky", "icon": "01d"}],
    "main": {"temp": 20.5, "humidity": 50, "pressure": 1013},
    "wind": {"speed": 5.0},
    "visibility": 10000,
    "dt": 1600000000
}

SAMPLE_MSG_TIMEMACHINE = {
    "data": [{
        "dt": 1600000000,
        "temp": 15.0,
        "humidity": 60,
        "pressure": 1012,
        "wind_speed": 4.0,
        "visibility": 9000,
        "weather": [{"main": "Clouds", "description": "few clouds", "icon": "02d"}]
    }]
}

@pytest.fixture
def mock_settings():
    with patch("app.services.weather_service.settings") as mock:
        mock.open_weather_api_key_25 = "key25"
        mock.open_weather_api_key_30 = "key30"
        yield mock

@pytest.fixture
def mock_cache():
    with patch("app.services.weather_service.WeatherService._get_cache") as mock_get:
        cache_mock = MagicMock()
        mock_get.return_value = cache_mock
        yield cache_mock

@pytest.fixture
def mock_httpx_client():
    with patch("app.services.weather_service.httpx.AsyncClient") as mock_client:
        client_instance = AsyncMock()
        mock_client.return_value.__aenter__.return_value = client_instance
        yield client_instance

@pytest.mark.asyncio
async def test_is_enabled(mock_settings):
    assert WeatherService.is_enabled() is True

    mock_settings.open_weather_api_key_25 = None
    mock_settings.open_weather_api_key_30 = None
    assert WeatherService.is_enabled() is False

@pytest.mark.asyncio
async def test_validate_coordinates():
    # Valid
    WeatherService._validate_coordinates(45.0, 90.0)

    # Invalid
    with pytest.raises(ValueError):
        WeatherService._validate_coordinates(91.0, 0.0)
    with pytest.raises(ValueError):
        WeatherService._validate_coordinates(0.0, 181.0)

@pytest.mark.asyncio
async def test_fetch_weather_cache_hit(mock_settings, mock_cache):
    # Setup Cache Hit
    mock_cache.get.return_value = {
        "temp_c": 20.0,
        "temp_f": 68.0,
        "condition": "Sunny",
        "description": "Sunny day",
        "humidity": 50,
        "wind_speed": 5.0,
        "observed_at_utc": datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat()
    }

    result, provider = await WeatherService.fetch_weather(10.0, 20.0)

    assert result is not None
    assert result.temp_c == 20.0
    assert provider == "openweather-current" # Default if no date provided
    mock_cache.get.assert_called_once()

@pytest.mark.asyncio
async def test_fetch_current_weather_api(mock_settings, mock_cache, mock_httpx_client):
    # Setup Cache Miss
    mock_cache.get.return_value = None

    # Setup API Response
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = SAMPLE_MSG_CURRENT
    mock_httpx_client.get.return_value = resp

    result, provider = await WeatherService.fetch_weather(10.0, 20.0)

    assert result is not None
    assert result.temp_c == 20.5
    assert result.condition == "Clear"
    assert provider == "openweather-current"

    # Verify Cache Set
    mock_cache.set.assert_called_once()

@pytest.mark.asyncio
async def test_fetch_historic_weather_api(mock_settings, mock_cache, mock_httpx_client):
    mock_cache.get.return_value = None

    # Setup Historic Date (> 1 hour ago)
    past_date = datetime.now(timezone.utc) - timedelta(hours=2)

    # Setup API Response
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = SAMPLE_MSG_TIMEMACHINE
    mock_httpx_client.get.return_value = resp

    result, provider = await WeatherService.fetch_weather(10.0, 20.0, past_date)

    assert result is not None
    assert result.temp_c == 15.0
    assert provider == "openweather-timemachine"

    # Verify Cache Set
    mock_cache.set.assert_called_once()

@pytest.mark.asyncio
async def test_fetch_weather_api_error_401(mock_settings, mock_cache, mock_httpx_client):
    mock_cache.get.return_value = None

    # Setup 401 Error
    resp = MagicMock()
    resp.status_code = 401
    resp.text = "Unauthorized"

    error = httpx.HTTPStatusError("401 Unauthorized", request=MagicMock(), response=resp)
    mock_httpx_client.get.side_effect = error

    with pytest.raises(ValueError, match="Invalid OpenWeather API Key"):
        await WeatherService.fetch_weather(10.0, 20.0)

@pytest.mark.asyncio
async def test_fetch_weather_api_error_500(mock_settings, mock_cache, mock_httpx_client):
    mock_cache.get.return_value = None

    # Setup 500 Error
    resp = MagicMock()
    resp.status_code = 500
    resp.text = "Internal Server Error"

    error = httpx.HTTPStatusError("500 Error", request=MagicMock(), response=resp)
    mock_httpx_client.get.side_effect = error

    with pytest.raises(httpx.HTTPStatusError):
        await WeatherService.fetch_weather(10.0, 20.0)
