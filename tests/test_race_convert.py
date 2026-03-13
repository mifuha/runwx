from __future__ import annotations

from pathlib import Path

from runwx.adapters.races.io_event_json import load_event_json
from runwx.adapters.races.io_results_csv import load_results_csv
from runwx.services.race_convert import results_to_runs


def test_results_to_runs_normalizes_duration_and_distance():
    event = load_event_json(Path("data") / "sample_event.json")
    results = load_results_csv(Path("data") / "sample_results.csv", event_id=event.event_id)

    runs = results_to_runs(event, results)

    assert len(runs) == 5
    assert runs[0].duration_s == 1320
    assert runs[0].distance_m == event.distance_m
    # all runs use event start time (UTC normalization handled in domain)
    assert runs[0].started_at.tzinfo is not None