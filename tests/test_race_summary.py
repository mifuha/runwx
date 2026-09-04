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


def test_summarize_results_top_n_equals_1_matches_best():
    results = [
        RaceResult(event_id="demo:event-001", duration_s=4200, athlete_id="a4"),
        RaceResult(event_id="demo:event-001", duration_s=3600, athlete_id="a1"),
        RaceResult(event_id="demo:event-001", duration_s=3900, athlete_id="a3"),
        RaceResult(event_id="demo:event-001", duration_s=3720, athlete_id="a2"),
        RaceResult(event_id="demo:event-001", duration_s=4500, athlete_id="a5"),
    ]

    summary = summarize_results(results, top_n=1)

    assert summary.best_duration_s == 3600
    assert summary.top_n_median_duration_s == 3600.0


def test_summarize_results_rejects_non_positive_top_n():
    results = [RaceResult(event_id="demo:event-001", duration_s=3600, athlete_id="a1")]

    with pytest.raises(ValueError, match="top_n must be positive"):
        summarize_results(results, top_n=0)

    with pytest.raises(ValueError, match="top_n must be positive"):
        summarize_results(results, top_n=-1)


def test_summarize_results_top_n_greater_than_len_results_uses_all_results():
    # For `top_n` larger than the field size, `top_n_median_duration_s` should match
    # `median_duration_s` since the "top N" slice is effectively the entire set.
    results = [
        RaceResult(event_id="demo:event-001", duration_s=4200, athlete_id="a4"),
        RaceResult(event_id="demo:event-001", duration_s=3600, athlete_id="a1"),
        RaceResult(event_id="demo:event-001", duration_s=3900, athlete_id="a3"),
    ]

    summary = summarize_results(results, top_n=10)

    assert summary.median_duration_s == 3900.0
    assert summary.top_n_median_duration_s == summary.median_duration_s


def test_summarize_results_even_length_median_behavior():
    # Median for even length is the average of the two middle values.
    # Durations sorted: [3600, 3800, 4000, 4200]
    results = [
        RaceResult(event_id="demo:event-001", duration_s=4200, athlete_id="a4"),
        RaceResult(event_id="demo:event-001", duration_s=3600, athlete_id="a1"),
        RaceResult(event_id="demo:event-001", duration_s=3800, athlete_id="a2"),
        RaceResult(event_id="demo:event-001", duration_s=4000, athlete_id="a3"),
    ]

    summary = summarize_results(results, top_n=2)

    assert summary.finisher_count == 4
    assert summary.best_duration_s == 3600
    assert summary.median_duration_s == 3900.0  # average(3800, 4000)
    assert summary.top_n_median_duration_s == 3700.0  # average(3600, 3800)