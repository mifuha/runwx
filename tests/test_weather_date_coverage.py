from datetime import date, datetime, timedelta, timezone

import pytest

from runwx.domain.models import Run, WeatherObs
from runwx.services.pipeline_open_meteo import enrich_runs_with_open_meteo


class DateFilteredClient:
    """A saved weather source that returns only the requested UTC dates."""

    def __init__(self, observations):
        self.observations = observations
        self.calls = []

    def fetch_weather_obs(self, *, latitude, longitude, start_date, end_date):
        self.calls.append((latitude, longitude, start_date, end_date))
        return [
            obs for obs in self.observations
            if start_date <= obs.observed_at.astimezone(timezone.utc).date() <= end_date
        ]


def observation_at(timestamp):
    return WeatherObs(
        observed_at=datetime.fromisoformat(timestamp),
        temp_c=8.0,
        wind_mps=3.0,
        precipitation_mm=0.0,
        humidity_pct=70.0,
    )


@pytest.mark.parametrize(
    ("started_at", "duration_s", "gap_minutes", "weather_at", "first_date", "last_date"),
    [
        pytest.param(
            "2026-02-01T23:45:00+00:00", 3600, 30, "2026-02-02T00:00:00+00:00",
            "2026-02-01", "2026-02-02", id="midpoint-crosses-midnight",
        ),
        pytest.param(
            "2026-02-02T00:05:00+00:00", 1200, 90, "2026-02-01T23:00:00+00:00",
            "2026-02-01", "2026-02-02", id="gap-reaches-previous-day",
        ),
        pytest.param(
            "2026-02-01T23:10:00+00:00", 1200, 45, "2026-02-02T00:00:00+00:00",
            "2026-02-01", "2026-02-02", id="gap-reaches-next-day",
        ),
        pytest.param(
            "2026-02-02T00:10:00+02:00", 1200, 30, "2026-02-01T22:00:00+00:00",
            "2026-02-01", "2026-02-01", id="dates-are-utc-not-local",
        ),
        pytest.param(
            "2026-02-01T23:30:00+00:00", 86400, 30, "2026-02-02T12:00:00+00:00",
            "2026-02-02", "2026-02-02", id="long-run-uses-midpoint-date",
        ),
        pytest.param(
            "2026-02-01T23:30:00+00:00", 3600, 0, "2026-02-02T00:00:00+00:00",
            "2026-02-02", "2026-02-02", id="zero-gap-at-exact-midnight",
        ),
    ],
)
def test_requested_dates_cover_the_midpoint_matching_window(
    started_at, duration_s, gap_minutes, weather_at, first_date, last_date
):
    run = Run(datetime.fromisoformat(started_at), duration_s, distance_m=5000)
    observation = observation_at(weather_at)
    client = DateFilteredClient([observation])

    result = enrich_runs_with_open_meteo(
        [run], latitude=51.5, longitude=-0.1, client=client,
        max_gap=timedelta(minutes=gap_minutes),
    )

    assert client.calls == [
        (51.5, -0.1, date.fromisoformat(first_date), date.fromisoformat(last_date))
    ]
    assert len(result.enriched) == 1
    assert result.enriched[0].run == run
    assert result.enriched[0].weather == observation
    assert result.skipped == ()


@pytest.mark.parametrize("has_distant_observation", [False, True], ids=["missing", "too-far"])
def test_missing_eligible_weather_remains_an_explicit_skip(has_distant_observation):
    run = Run(datetime(2026, 2, 1, 23, 45, tzinfo=timezone.utc), 3600, 5000)
    observations = (
        [observation_at("2026-02-02T03:00:00+00:00")] if has_distant_observation else []
    )
    client = DateFilteredClient(observations)

    result = enrich_runs_with_open_meteo(
        [run], latitude=51.5, longitude=-0.1, client=client,
    )

    assert client.calls == [(51.5, -0.1, date(2026, 2, 1), date(2026, 2, 2))]
    assert result.enriched == ()
    assert len(result.skipped) == 1
    assert result.skipped[0].run == run
    assert result.skipped[0].reason == "No weather within 0:30:00"


def test_batch_bounds_use_all_midpoints_independently_of_start_order():
    runs = [
        Run(datetime(2026, 2, 1, 12, tzinfo=timezone.utc), 72 * 3600, 100_000),
        Run(datetime(2026, 2, 2, 0, 5, tzinfo=timezone.utc), 600, 5000),
    ]
    later_weather = observation_at("2026-02-03T00:00:00+00:00")
    earlier_weather = observation_at("2026-02-02T00:00:00+00:00")
    client = DateFilteredClient([earlier_weather, later_weather])

    result = enrich_runs_with_open_meteo(
        runs, latitude=51.5, longitude=-0.1, client=client,
    )

    assert client.calls == [(51.5, -0.1, date(2026, 2, 1), date(2026, 2, 3))]
    assert [row.weather for row in result.enriched] == [later_weather, earlier_weather]
    assert result.skipped == ()


@pytest.mark.parametrize("has_runs", [False, True])
def test_negative_matching_window_is_rejected_before_fetching_weather(has_runs):
    runs = [Run(datetime(2026, 2, 1, 12, tzinfo=timezone.utc), 3600, 5000)] if has_runs else []
    client = DateFilteredClient([])

    with pytest.raises(ValueError, match="max_gap must be non-negative"):
        enrich_runs_with_open_meteo(
            runs, latitude=51.5, longitude=-0.1, client=client,
            max_gap=timedelta(seconds=-1),
        )

    assert client.calls == []
