import pytest

from runwx.domain.race import RaceResult
from runwx.services.race_summary import EventSummary, summarize_results


def test_summarize_results_computes_basic_event_stats():
    results = [
        RaceResult(event_id="demo:event-001", duration_s=4200, athlete_id="a4"),
        RaceResult(event_id="demo:event-001", duration_s=3600, athlete_id="a1"),
        RaceResult(event_id="demo:event-001", duration_s=3900, athlete_id="a3"),
        RaceResult(event_id="demo:event-001", duration_s=3720, athlete_id="a2"),
        RaceResult(event_id="demo:event-001", duration_s=4500, athlete_id="a5"),
    ]

    summary = summarize_results(results, top_n=3)

    assert summary == EventSummary(
        finisher_count=5,
        mean_duration_s=3984.0,
        median_duration_s=3900.0,
        best_duration_s=3600,
        top_n_median_duration_s=3720.0,
    )


def test_summarize_results_rejects_empty_results():
    with pytest.raises(ValueError, match="results must not be empty"):
        summarize_results([])