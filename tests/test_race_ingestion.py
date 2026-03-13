from __future__ import annotations

from pathlib import Path

from runwx.adapters.races.io_event_json import load_event_json
from runwx.adapters.races.io_results_csv import load_results_csv


def test_load_event_and_results_from_sample_files():
    event = load_event_json(Path("data") / "sample_event.json")
    results = load_results_csv(Path("data") / "sample_results.csv", event_id=event.event_id)

    assert event.distance_m == 5000
    assert len(results) == 5
    assert results[0].duration_s == 1320
    assert results[0].event_id == event.event_id