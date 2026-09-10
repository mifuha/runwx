from __future__ import annotations

from datetime import date, datetime, timezone

import json

import httpx
from pydantic import ValidationError
import pytest

from runwx.adapters.weather.open_meteo import OpenMeteoClient
from runwx.adapters.weather.schemas import OpenMeteoArchiveResponse


def test_fetch_hourly_requests_wind_speed_in_metres_per_second(monkeypatch):
    requested_params = {}

    def handler(request: httpx.Request) -> httpx.Response:
        requested_params.update(dict(request.url.params))
        return httpx.Response(
            200,
            json={
                "latitude": 51.5,
                "longitude": -0.1,
                "timezone": "UTC",
                "utc_offset_seconds": 0,
                "hourly": {
                    "time": [],
                    "temperature_2m": [],
                    "relative_humidity_2m": [],
                    "precipitation": [],
                    "wind_speed_10m": [],
                },
            },
        )

    transport = httpx.MockTransport(handler)
    client_class = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: client_class(transport=transport, **kwargs),
    )

    OpenMeteoClient().fetch_hourly(
        latitude=51.5,
        longitude=-0.1,
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 1),
    )

    assert requested_params["wind_speed_unit"] == "ms"


def test_fetch_weather_obs_returns_translated_weather_obs(monkeypatch):
    payload = {
        "latitude": 51.5,
        "longitude": -0.1,
        "timezone": "UTC",
        "utc_offset_seconds": 0,
        "hourly": {
            "time": ["2026-02-01T10:00", "2026-02-01T11:00"],
            "temperature_2m": [7.2, 7.6],
            "relative_humidity_2m": [80.0, 78.0],
            "precipitation": [0.0, 0.2],
            "wind_speed_10m": [3.1, 3.4],
        },
    }
    response = OpenMeteoArchiveResponse.model_validate(payload)

    called = {}

    def fake_fetch_hourly(self, *, latitude, longitude, start_date, end_date):
        called["args"] = (latitude, longitude, start_date, end_date)
        return response

    monkeypatch.setattr(OpenMeteoClient, "fetch_hourly", fake_fetch_hourly)

    client = OpenMeteoClient(timeout_s=5.0)
    obs = client.fetch_weather_obs(
        latitude=51.5,
        longitude=-0.1,
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 1),
    )

    assert called["args"] == (
        51.5,
        -0.1,
        date(2026, 2, 1),
        date(2026, 2, 1),
    )

    assert len(obs) == 2

    assert obs[0].observed_at == datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc)
    assert obs[0].temp_c == 7.2
    assert obs[0].wind_mps == 3.1
    assert obs[0].precipitation_mm == 0.0
    assert obs[0].humidity_pct == 80.0

    assert obs[1].observed_at == datetime(2026, 2, 1, 11, 0, tzinfo=timezone.utc)
    assert obs[1].temp_c == 7.6
    assert obs[1].wind_mps == 3.4
    assert obs[1].precipitation_mm == 0.2
    assert obs[1].humidity_pct == 78.0


@pytest.fixture
def mock_archive_http(monkeypatch):
    """Use HTTPX's real client with deterministic responses and check cleanup."""
    client_class = httpx.Client
    clients = []

    def install(handler):
        requests = []

        def record_request(request):
            requests.append(request)
            return handler(request)

        transport = httpx.MockTransport(record_request)

        def create_client(**kwargs):
            client = client_class(transport=transport, **kwargs)
            clients.append(client)
            return client

        monkeypatch.setattr(httpx, "Client", create_client)
        return requests

    yield install
    assert clients and all(client.is_closed for client in clients)


@pytest.mark.parametrize("status_code", [429, 500])
def test_fetch_hourly_propagates_http_errors_before_decoding_json(mock_archive_http, status_code):
    requests = mock_archive_http(
        lambda request: httpx.Response(status_code, text="provider unavailable")
    )

    with pytest.raises(httpx.HTTPStatusError) as error:
        OpenMeteoClient().fetch_hourly(
            latitude=51.5, longitude=-0.1,
            start_date=date(2026, 2, 1), end_date=date(2026, 2, 1),
        )

    assert error.value.response.status_code == status_code
    assert error.value.response.text == "provider unavailable"
    assert error.value.request.url.host == "archive-api.open-meteo.com"
    assert error.value.request.method == "GET"
    assert len(requests) == 1


def test_fetch_hourly_propagates_timeout_without_retry(mock_archive_http):
    def timed_out(request):
        raise httpx.ReadTimeout("timed out reading archive", request=request)

    requests = mock_archive_http(timed_out)
    with pytest.raises(httpx.ReadTimeout, match="timed out reading archive") as error:
        OpenMeteoClient(timeout_s=2.5).fetch_hourly(
            latitude=51.5, longitude=-0.1,
            start_date=date(2026, 2, 1), end_date=date(2026, 2, 1),
        )

    assert len(requests) == 1
    assert error.value.request is requests[0]
    assert requests[0].extensions["timeout"] == {
        "connect": 2.5, "read": 2.5, "write": 2.5, "pool": 2.5,
    }


def test_fetch_hourly_rejects_malformed_json(mock_archive_http):
    malformed = '{"hourly":'
    requests = mock_archive_http(lambda request: httpx.Response(200, text=malformed))

    with pytest.raises(json.JSONDecodeError) as error:
        OpenMeteoClient().fetch_hourly(
            latitude=51.5, longitude=-0.1,
            start_date=date(2026, 2, 1), end_date=date(2026, 2, 1),
        )

    assert error.value.doc == malformed
    assert len(requests) == 1


def test_fetch_hourly_rejects_inconsistent_hourly_lengths(mock_archive_http):
    payload = {
        "latitude": 51.5, "longitude": -0.1,
        "timezone": "UTC", "utc_offset_seconds": 0,
        "hourly": {
            "time": ["2026-02-01T10:00", "2026-02-01T11:00"],
            "temperature_2m": [7.2],
            "relative_humidity_2m": [80.0, 78.0],
            "precipitation": [0.0, 0.2],
            "wind_speed_10m": [3.1, 3.4],
        },
    }
    requests = mock_archive_http(lambda request: httpx.Response(200, json=payload))

    with pytest.raises(ValidationError, match="Hourly arrays must all be the same length") as error:
        OpenMeteoClient().fetch_hourly(
            latitude=51.5, longitude=-0.1,
            start_date=date(2026, 2, 1), end_date=date(2026, 2, 1),
        )

    details = error.value.errors()
    assert len(details) == 1
    assert details[0]["loc"] == ("hourly",)
    assert details[0]["type"] == "value_error"
    assert "'temperature_2m': 1" in details[0]["msg"]
    assert "'time': 2" in details[0]["msg"]
    assert len(requests) == 1
