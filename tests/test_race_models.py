from __future__ import annotations

from datetime import datetime, timezone

import pytest

from runwx.domain.race import RaceEvent, RaceResult


def test_race_result_to_run_uses_event_start_and_distance():
    event = RaceEvent(
        source="demo",
        source_event_id="e1",
        name="Test 5K",
        started_at=datetime(2026, 2, 1, 9, 0, tzinfo=timezone.utc),
        distance_m=5000,
        latitude=51.5,
        longitude=-0.1,
    )
    result = RaceResult(event_id=event.event_id, duration_s=1500, place=42)

    run = result.to_run(event)

    assert run.started_at == event.started_at
    assert run.distance_m == 5000
    assert run.duration_s == 1500


def test_race_result_to_run_rejects_event_mismatch():
    event = RaceEvent(
        source="demo",
        source_event_id="e1",
        name="Test 5K",
        started_at=datetime(2026, 2, 1, 9, 0, tzinfo=timezone.utc),
        distance_m=5000,
        latitude=51.5,
        longitude=-0.1,
    )
    result = RaceResult(event_id="demo:other", duration_s=1500)

    with pytest.raises(ValueError):
        result.to_run(event)