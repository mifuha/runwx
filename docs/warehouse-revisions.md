# Warehouse revision keys and selection

The four BigQuery tables and optional dbt selector have been validated with fully
synthetic race and weather inputs. The existing three analytical views still read
their original single export. The guarded selection writer has also passed a
bounded native BigQuery check: stale requests fail, failed updates roll back,
and an explicit selection change preserves candidate data.

## Table grain and keys

The [schema files](../dbt/contracts/revisions) use BigQuery's JSON schema format.
Their private dataset is `runwx_revision_demo`, separate from the first staging
table. These are the logical keys the publisher and tests must enforce:

| Table | One row means | Logical key |
| --- | --- | --- |
| `analysis_revisions` | One revision identity, expected quality counts, candidate digest and saved Python report. | `revision_id` |
| `revision_result_rows` | One candidate from that revision, including skipped/invalid rows. | `(revision_id, source_row_number)` |
| `revision_attempts` | One execution and its validation receipt. | `attempt_id` |
| `event_selections` | The explicitly chosen successful revision/attempt for one event. | `event_id` |

`source_row_id` alone is insufficient across analyses: changing top-N or weather
settings can reuse the same race snapshot and its row IDs. The revision key
distinguishes those analyses. Attempts do not become additional result rows.
An event ID identifies an edition; a correction keeps that event ID. No athlete
identity across snapshots is inferred.

The [export helper](../src/runwx/services/revision_export.py) calls the existing
result exporter, checks its hashes/event against the prepared revision, then adds
`revision_id`. The other fields and nested weather/settings records are unchanged.
Requested top-N stays in revision settings; it does not change individual rows.
This first warehouse contract requires a nonempty candidate set, consistent with
the existing single-export loader; rejected candidates still count as rows.

Metadata reuses the [local revision identity](revisions.md) and report. For the
candidate digest, serialise the complete rows in source order with
`canonical_json(rows)` and hash its UTF-8 bytes. `report_json` retains the original
report, including its paths and limitations. The publisher verifies loaded
content against these inputs and requires an existing warehouse receipt. The
digest identifies the prepared export; read-back comparison must account for
equivalent timestamp and numeric spellings through typed value normalisation.

## The selection boundary

The [selector](../dbt/models/revisions/selected_revision_results.sql) returns all
candidates for the selected revision. Keeping rejected rows lets later quality
counts reconcile; accepted-results filtering stays in the existing fact logic.
It carries revision settings/code identity alongside the existing export fields.

For the synthetic example, A and corrected B each contain five candidate rows.
There are four receipts: A's first run, B's first run, B's retry and an old A replay.
Selecting B should expose **five rows: three accepted, one skipped, one invalid**.
Two accepted rows have weather. Neither extra receipt adds a finisher.

The key condition is an existence check for the **specific selected receipt**:

```sql
where exists (
    select 1 from attempts a
    where a.attempt_id = s.successful_attempt_id
      and a.revision_id = r.revision_id
      and a.status = 'succeeded'
      and a.validation_scope = 'warehouse'
      -- The full model also requires validation code and invocation identifiers.
)
```

BigQuery's [`EXISTS`](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/subqueries#exists_subqueries)
tests whether a matching row exists. It does not add one output row per match.
BigQuery [does not enforce primary/foreign keys](https://docs.cloud.google.com/bigquery/docs/primary-foreign-keys),
so the selector also checks uniqueness of revision, selection and receipt keys.
It checks the complete candidate count, distinct contiguous row numbers, quality
counts and source identity before returning any rows from a selected revision.

A local report attempt has scope `local_report`. A warehouse validation records
`warehouse` success, with the validation-code hash and invocation ID, only after
candidate loading, data checks and report agreement succeed. The bounded validation
recorded those receipts manually; this is not yet an application command. The receipt
fixtures in the unit tests are fabricated test inputs, not execution evidence.
The Python source hash remains part of revision identity; the separate validation
hash identifies the checked dbt files; verification-query hashes are recorded
separately in the execution evidence.

## Failure behaviour and remaining work

An ambiguous selection or partial/duplicated selected candidate emits no rows and
fails [selection reconciliation](../dbt/tests/selected_revision_reconciles.sql).
This detects a broken pointer; it does not restore the previous selection.

The [guarded writer](../src/runwx/adapters/bigquery/selection.py) prepares a baseline
through the existing report and revision export. Before writing, it reads the
candidate directly from its metadata, result and receipt tables, independently of
the selector.
It requires complete agreement with the local rows, metadata, hashes, report and
the exact successful warehouse receipt, including validation hash/invocation.
Local receipt identifiers alone do not count as warehouse evidence.

It then uses one [BigQuery transaction](https://docs.cloud.google.com/bigquery/docs/transactions)
to recheck that candidate content and compare the event's current revision **and
attempt** with the caller's explicit expectation. Only then does it insert or
update one pointer. `expected=None` means no selection may exist. Duplicate pointers
are rejected. An already-selected, still-valid candidate returns `already_selected`
without another write. Replaying an analysis never invokes the writer automatically.

This is a serialized submission contract, not a distributed lock. Candidate data
and validation receipts must remain immutable after validation; snapshot isolation
does not prevent an outside writer changing them afterwards. No new table, loader,
validation receipt creator, dbt model or orchestration step is added.

## Calling and testing the writer

`prepare_selection(revision, race_html, weather_csv, ...)` is offline. Supply the
destination dataset, expected `Selection` (or explicit `None`), successful attempt
ID, validation-code SHA-256 and validation invocation ID. It reuses the current
processing code, so a revision prepared by different code must be reproduced in
its matching environment; new code creates a new revision identity. It currently
accepts synthetic inputs only, with a baseline limit of 1 MiB.

After candidate loading and real warehouse validation, `publish_selection(client,
prepared)` runs a read and a guarded write in `europe-west1`. Each query has a fresh
job ID, a 100 MiB billed limit, a 300-second timeout setting and no automatic retries.
Job IDs identify execution attempts; they are not logical revision IDs. The result
contains the selected event/revision/attempt and actual job IDs/byte statistics.
Input paths may differ in the saved report; all analytical fields and hashes must
agree. Typed row comparison permits equivalent UTC timestamp and numeric spellings.

A read-back mismatch sends no write. A transaction assertion failure rolls back
that transaction, leaving the prior pointer intact. A client exception after
submission is reported conservatively as `SelectionOutcomeUnknown`, with the job
ID: it may already have committed. Inspect that job and the pointer before another
submission; a timeout is not evidence of rollback. The Python exception retains
the original API error as its cause. No automatic retry or recovery loop is added.

The [focused tests](../tests/test_guarded_selection.py) block network access and use
the real SDK interfaces with a small stateful API fake. They check correction,
repeat, initial selection, malformed candidates/receipts, stale revision or attempt,
changes between read and write, and a lost response after commit. They do **not**
execute SQL or prove native transaction behaviour. The separate
[native writer validation](#verified-guarded-writer) below covers the update path
and rollback; the earlier selector validation covers the dbt model.

The existing loader does not load these new contracts. The
[verified analytical integration](dbt-models.md#verified-selected-revision-run) now carries the
revision's saved top-N setting into staging/fact/summary and partitions summaries
by event/revision. The deployed analytical views now use selected rows and match
the saved Python baseline. Statistical definitions are unchanged.

## Local checks

Run the Python export tests in the report environment:

```bash
python -m pytest -q tests/test_revision_export.py tests/test_revisions.py tests/test_guarded_selection.py
```

Parse the optional model and its native unit/data test definitions using the
[separate dbt environment](dbt-models.md#local-setup-and-checks):

```bash
.venv-dbt/bin/dbt --no-partial-parse parse \
  --project-dir dbt --profiles-dir dbt --target local \
  --vars '{"enable_revision_preview": true}'
```

The selector, its four sources and its tests are disabled by default. Normal dbt
parsing still has three models, fourteen data tests and seven unit tests. The
preview now also switches the analytical models to selected rows: four models,
fifteen data tests and twenty unit cases (twelve selector, eight integration).
The selector cases cover retries/replay, failed or local-only receipts, duplicate
keys and partial candidates. The eight integration cases have also passed native execution.

Parsing and local SQL syntax checks do not execute these assertions or prove
BigQuery behaviour. The cloud run below executed the native tests.

## Verified BigQuery validation

On 9 September 2026, two targeted container builds passed in `europe-west1`.
Each executed **12 native unit tests, one reconciliation data test and one view**.
The first ran with no selection; the second checked the populated selection.
The [evidence JSON](evidence/revision-selector-validation.json) contains the actual
test names/results, image and invocation IDs, queries, input hashes and selected rows.

| Check | Result |
| --- | --- |
| Complete typed input read-back | Two revisions, ten candidates and four local receipts matched. |
| Selected correction | Five candidates: three accepted, one skipped, one invalid. |
| Weather coverage | Two matched accepted finishers; one without weather. |
| Accepted durations | 3600, 6600 and 14400 seconds, matching the local correction. |
| Populated selection reconciliation | Zero errors. |
| Read-only local-receipt substitution | Zero exposed rows; saved valid selection still returned five. |

Both race snapshots and the weather are synthetic, not historical evidence.
The saved corrected Python report has median and top-N median duration 6600 seconds
(requested N=20, effective N=3). This validation compared every selected result field;
it did not create a new summary model or change the existing metric definition.
UTC timestamp spelling and equivalent numeric representations were normalized
before comparison. Paths remain in the saved report; execution IDs are separate.

Terraform created only the private `runwx_revision_demo` dataset and four protected
tables, using [revision_validation.tf](../infra/gcp/revision_validation.tf).
Its `enable_revision_validation` flag defaults to false; the deployed configuration
retains it as true. dbt created `runwx_dbt_demo.selected_revision_results`.
The tables hold two revisions, ten candidates, six receipts (four local, two warehouse)
and one selection. Existing source data and the three analytical views were unchanged.

Only after the first build and full input read-back passed were the two warehouse
receipts appended and the correction selected. The recorded validation hash covers
the dbt input files; the verification queries have their own hashes. The image was
built from the evidence's base commit. A later test-comment edit changes no SQL.
This one-off validation procedure is not a reusable loader or publication service.

The targeted command inside the [dbt container](dbt-models.md#cloud-execution) was:

```bash
dbt --no-partial-parse build --profiles-dir . --target cloud \
  --vars '{"enable_revision_preview":true}' --select selected_revision_results
```

The window used two builds, three verification queries and five small batch loads.
All 75 query jobs succeeded: 35,049 bytes processed and 209,715,200 bytes billed
(200 MiB), including dbt's internal queries. Each query retained the 100 MiB billed
limit; the profile used one thread, a 300-second wait and no job retries.
Billed-byte statistics are not a currency invoice; actual charges were not verified.
No temporary test tables remained, and the final Terraform plan reported no changes.
No billing, API, IAM, Cloud Run or existing-resource cleanup changes were made.

## Verified guarded writer

On 9 September 2026, the writer at commit `f7dcc43` was exercised through the local
Python BigQuery SDK in `europe-west1`. The [execution evidence](evidence/guarded-selection-validation.json)
contains the exact SQL, job IDs, transaction records, source hashes and final rows.
It reuses the two existing synthetic revisions and their real warehouse receipts;
there were no new data uploads, resources, model changes or dbt builds.

The original processing source was checked out as an archive under `/tmp` to
reproduce both baselines offline. Their revision IDs, code hash and candidate
digests matched the earlier validation. The new writer consumed those verified
bundles as `PreparedSelection` values; it did not relabel old results as new-code
output. Stored report paths could differ; analytical content had to match.

| Native check | Observed result |
| --- | --- |
| Select the already-selected correction B | `already_selected`; no update. |
| Request A while incorrectly expecting no selection | `selection changed`; B remains selected. |
| Inject failure after updating to A, before commit | One `UPDATE`, then `ROLLBACK_TRANSACTION`; B and its rows remain intact. |
| Select A while expecting B | One guarded update; all five selected rows match A's baseline. |
| Restore B while expecting A | One guarded update; exact original pointer and selected rows restored. |

The fault case adds `ASSERT FALSE` just before `COMMIT TRANSACTION` in the submitted
test SQL. The application SQL is unchanged. The native job metadata confirms the
update and rollback, and a separate read-back confirms the preserved pointer.
All metadata, ten candidate rows and six receipts matched before and after.

Both selections have five candidates: three accepted, one skipped and one invalid,
with two accepted finishers matched to weather. Median and top-N median duration
are 7,200 seconds for A and 6,600 for B. These are synthetic corrections to one
edition, not real historical comparisons. The final state is B.

The window used **14 top-level query jobs**: twelve succeeded and two failed as
intended. Their 44 child jobs are retained as transaction evidence. Parent totals
report 181,044 bytes processed and 566,231,040 bytes billed (540 MiB); child totals
are not added again. Every submission retained the 100 MiB query limit, 300-second
timeout setting and zero retries. Actual currency charges were not verified.

Initial insertion, simultaneous writers and response-loss recovery were not tested
in BigQuery here. The Python tests cover additional cases using an API fake.
This writer validation did not change the staging/fact/mart views. Their subsequent
integration with selected revisions passed native validation; see
[the dbt execution evidence](dbt-models.md#verified-selected-revision-run).
