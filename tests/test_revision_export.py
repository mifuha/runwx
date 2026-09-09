from collections import Counter
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import json
import re
import socket

import httpx
import pytest

from runwx.domain.revisions import canonical_json
from runwx.adapters.bigquery.result_load import _normalise_fields
from runwx.services.offline_report import build_offline_report
from runwx.services.result_export import build_result_rows
from runwx.services.revision_export import build_revision_rows
from runwx.services.revisions import prepare_revision


RACE = Path("data/sample_race_synthetic.html")
CORRECTED = Path("data/sample_race_synthetic_corrected.html")
WEATHER = Path("data/sample_lydd_weather_synthetic.csv")
SETTINGS = dict(course_id="runwx-synthetic-half", distance_m=21097,
                timezone_name="Europe/London", weather_kind="synthetic")


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("revision export attempted network access")

    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo"):
        monkeypatch.setattr(socket, name, forbidden)
    monkeypatch.setattr(httpx.Client, "request", forbidden)


def prepare(race=RACE, **changes):
    return prepare_revision(
        race, WEATHER, event_id="eventrac:900001",
        weather_source_id="runwx:synthetic-hourly-weather-demo",
        snapshot_scope="complete", race_kind="synthetic", **(SETTINGS | changes),
    )


def test_revision_export_reuses_all_candidate_fields_and_repeats_without_attempt_rows():
    revision = prepare()
    first = build_revision_rows(revision, RACE, WEATHER)
    repeat = build_revision_rows(revision, RACE, WEATHER)
    legacy = build_result_rows(RACE, WEATHER, race_kind="synthetic", **SETTINGS)
    report = build_offline_report(RACE, WEATHER, **SETTINGS)

    assert canonical_json(first) == canonical_json(repeat)
    assert [{k: v for k, v in row.items() if k != "revision_id"} for row in first] == legacy
    assert len({(r["revision_id"], r["source_row_number"]) for r in first}) == 5
    assert all("attempt_id" not in row for row in first)
    assert Counter(r["validation_status"] for r in first) == {
        "accepted": 3, "skipped": 1, "invalid": 1,
    }
    assert sum(r["weather_match_status"] == "matched" for r in first) == report[
        "weather_coverage"
    ]["matched_count"] == 2


def test_same_source_rows_can_belong_to_two_analysis_revisions():
    default = build_revision_rows(prepare(), RACE, WEATHER)
    top_one = build_revision_rows(prepare(top_n=1), RACE, WEATHER)
    assert [r["source_row_id"] for r in default] == [r["source_row_id"] for r in top_one]
    assert len({(r["revision_id"], r["source_row_number"]) for r in default + top_one}) == 10
    assert [r["duration_s"] for r in default] == [r["duration_s"] for r in top_one]


def test_complete_correction_is_a_separate_candidate_with_unchanged_coverage():
    a = build_revision_rows(prepare(), RACE, WEATHER)
    b = build_revision_rows(prepare(CORRECTED), CORRECTED, WEATHER)
    assert len(a) == len(b) == 5
    assert [r["duration_s"] for r in b] == [3600, 6600, 14400, None, None]
    assert [r["weather_match_status"] for r in a] == [r["weather_match_status"] for r in b]
    assert {r["revision_id"] for r in a}.isdisjoint({r["revision_id"] for r in b})


def test_changed_matching_setting_keeps_finishers_and_changes_revision():
    broad = build_revision_rows(prepare(), RACE, WEATHER)
    exact = build_revision_rows(prepare(max_gap=timedelta(0)), RACE, WEATHER)
    assert broad[0]["revision_id"] != exact[0]["revision_id"]
    assert [r["duration_s"] for r in broad] == [r["duration_s"] for r in exact]
    assert sum(r["weather_match_status"] == "matched" for r in broad) == 2
    assert sum(r["weather_match_status"] == "matched" for r in exact) == 1


def test_different_input_or_code_cannot_be_exported_under_old_revision():
    revision = prepare()
    with pytest.raises(ValueError, match="sources differ"):
        build_revision_rows(revision, CORRECTED, WEATHER)
    with pytest.raises(ValueError, match="processing code"):
        build_revision_rows(replace(revision, code_sha256="0" * 64), RACE, WEATHER)


def test_candidate_export_matches_the_proposed_bigquery_row_schema():
    schema = json.loads(Path('dbt/contracts/revisions/revision_result_rows.schema.json').read_text())
    rows = build_revision_rows(prepare(), RACE, WEATHER)
    assert [_normalise_fields(row, schema) for row in rows] == rows


def test_empty_candidate_set_is_not_prepared_for_this_first_warehouse_contract(tmp_path):
    race = tmp_path / 'empty.html'
    race.write_text(re.sub(r'<tbody>.*?</tbody>', '<tbody></tbody>', RACE.read_text(), flags=re.S))
    with pytest.raises(ValueError, match="no Eventrac candidate result rows found"):
        build_revision_rows(prepare(race), race, WEATHER)
