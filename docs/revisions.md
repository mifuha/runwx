# Local revisions and selection

The local Python contract separates an analysis, its executions and the report
chosen for an event. It reuses the existing offline report. The warehouse loader
and three dbt views still use the original single-export contract.

| Record | What it means |
| --- | --- |
| Revision | One event/source identity, exact race and weather bytes, interpretation settings and Python source version. Its ID is a SHA-256 of that identity. |
| Attempt | One execution of a revision, with a fresh ID, input paths and running/succeeded/failed status. Repeating an analysis creates another attempt. |
| Selection | An explicit reference from an event to one successful revision and its successful attempt. Running an analysis never changes this reference. |

A changed input hash, source identity, setting or code hash gives a new revision.
Moving identical files leaves it unchanged. The code hash covers relative paths
and bytes of all installed `runwx` Python source files, including uncommitted edits;
it does not capture dependency versions, SQL models or the interpreter. Use a fresh
Python process after editing code.

## Try the synthetic correction

From the repository root, after the [usual setup](../README.md#quickstart):

```bash
python - <<'PY'
from pathlib import Path
from runwx.services.revisions import RevisionSession, prepare_revision

weather = Path("data/sample_lydd_weather_synthetic.csv")
original = Path("data/sample_race_synthetic.html")
corrected = Path("data/sample_race_synthetic_corrected.html")
options = dict(
    event_id="eventrac:900001", weather_source_id="runwx:synthetic-hourly-weather-demo",
    snapshot_scope="complete", race_kind="synthetic", weather_kind="synthetic",
    course_id="runwx-synthetic-half", distance_m=21097, timezone_name="Europe/London",
)
session = RevisionSession()
a = prepare_revision(original, weather, **options)
b = prepare_revision(corrected, weather, **options)
session.run(a, original, weather)
session.select(a.event_id, a.revision_id)

def show(label):
    report = session.selected_report(a.event_id)
    summary, coverage = report["race_summary"], report["weather_coverage"]
    print(label, summary["median_duration_s"], summary["finisher_count"],
          f'{coverage["matched_count"]}/{coverage["accepted_result_count"]}')

print("Fully synthetic race correction and weather; not historical evidence.")
show("original:")
session.run(b, corrected, weather)
show("correction awaiting selection:")
session.select(b.event_id, b.revision_id)
show("correction selected:")
session.run(a, original, weather)
show("old revision replayed:")
PY
```

Output columns are median duration in seconds, finisher count and weather coverage:

```text
Fully synthetic race correction and weather; not historical evidence.
original: 7200 3 2/3
correction awaiting selection: 7200 3 2/3
correction selected: 6600 3 2/3
old revision replayed: 6600 3 2/3
```

The correction is a saved, complete replacement of the five synthetic candidates.
Its middle accepted time changes from 2:00 to 1:50. This is a correction to the
same edition, not a historical comparison or a claim about a real athlete.
The top-N statistic remains the existing **median** of the fastest N finishers.

## Success and selection boundary

`RevisionSession.run()` records an attempt, calls `build_offline_report()`, checks
input identity and report accounting, then retains a successful candidate. It
does not change selection. A repeat with different analytical output fails;
input file paths are the only report fields ignored in that comparison. Earlier
successful reports keep their original paths and remain accessible by revision ID.
Returned reports are copies, so editing one cannot alter a stored candidate.

`select(event_id, revision_id)` requires an existing successful candidate for that
event. Explicitly selecting an older successful revision is allowed; merely
replaying it cannot roll back the selection. A failed retry also leaves an earlier
success eligible for selection, with the original successful attempt as evidence.

Skipped and invalid result rows retain their usual accounting. They are not a
whole-run failure. A page/CSV error, mismatched source hash or broken report contract
fails the attempt and raises the error; it cannot replace the selected report.

## Limits and next boundary

This is an in-memory, sequential contract. Records last for the Python process;
saved input fixtures remain on disk. It does not provide durable publication,
crash recovery, automatic retries, concurrent-run guarantees or cloud validation.
Snapshot completeness is an explicit caller assertion; this demonstration knows
the complete synthetic set. Real snapshots need a completeness check before using
the `complete` declaration. Partial/delta or unverified inputs are refused.

The [warehouse keys and selection query](warehouse-revisions.md) have also been
validated in BigQuery: candidates by revision ID, separate attempts and an
event-to-revision reference. Local-only successes remain hidden. A guarded durable
publication writer is still needed; the in-memory session is not that writer.
No cross-revision athlete identity is inferred from a name, place or row number.

Run the [contract tests](../tests/test_revisions.py):

```bash
python -m pytest -q tests/test_revisions.py
```

The correction/replay test is the main example. Other tests cover failed attempts,
retry identity, path relocation, changed inputs/settings/code, event mismatch,
report-accounting failure and conflicting repeats. Network requests are blocked.
