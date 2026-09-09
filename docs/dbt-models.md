# First dbt models

Original single-export mode: **executed and verified in BigQuery on 8 September 2026**. The source is
the [verified synthetic export](bigquery-staging.md) in
`runwx_staging.synthetic_results`. All three views and all 21 dbt tests passed
in the corrected container build. See the [execution evidence](#verified-cloud-run).
Selected-revision integration is **executed and verified in BigQuery on
9 September 2026**. The deployed analytical views now read selected revisions.
See the [selected-mode evidence](#verified-selected-revision-run).

dbt connects SQL models through `source()` and `ref()`, builds them in dependency
order and runs their tests. These three models are configured as ordinary views:
they save SQL and recompute results when queried, rather than storing new result rows.

| Model | What one row represents |
| --- | --- |
| [stg_race_results](../dbt/models/stg_race_results.sql) | One candidate row, with settings and weather fields flattened into columns. |
| [fct_race_results](../dbt/models/fct_race_results.sql) | One accepted finisher, including finishers without matched weather. |
| [mart_event_summary](../dbt/models/mart_event_summary.sql) | One event/export context and its quality counts, coverage and metrics. |

## Metric and input contract

Average pace is `duration_s / (distance_m / 1000.0)`, in **seconds per kilometre**.
Both whole-field and top-N statistics use exact medians. Top-N means the fastest
`min(N, finisher_count)` finishers, ordered by duration then original row number;
N defaults to 20 and must be a positive integer. The whole-field mean remains a
separate duration metric. This preserves the [Python metric contract](bigquery-staging.md#metric-contract).

Missing weather never removes an accepted result. Coverage uses all accepted
finishers as its denominator. Source hashes, event/distance, synthetic labels and
interpretation settings remain attached; the mart also names units and requested/effective N.

One source table contains one complete export. The [context guard](../dbt/macros/context_columns.sql)
distinguishes the full context, including nullable settings. Empty or mixed contexts
produce no summary and fail a data test. An export containing only rejected rows
still produces quality counts, with null performance metrics and null coverage.

The [unit cases](../dbt/models/unit_tests.yml) use SQL fixtures derived from the
saved synthetic inputs and expected values from the existing Python summary.
They cover flattening, unmatched finishers, equal finish times, top-N medians,
all-rejected inputs and mixed settings. [Data tests](../dbt/tests/) check identity,
row/outcome consistency and source → staging → fact → mart reconciliation.
**These demonstrations are synthetic, not historical race findings.**
The Python baseline expects five candidates, three accepted finishers and weather
coverage of 2/3. Median duration is 7,200 seconds (341.28 seconds/km); the fastest
two have a median of 5,400 seconds. BigQuery reproduced these values.

## Selected-revision input

With `enable_revision_preview: true`, the same three models read:

```text
selected_revision_results → stg_race_results → fct_race_results → mart_event_summary
```

The [input switch](../dbt/macros/race_results_input.sql) chooses the selector instead
of the original staging table. Staging retains every selected candidate and adds
`revision_id`, `code_sha256` and `top_n_requested` from saved revision settings.
The fact still filters only on acceptance. The mart groups counts, ranking and
medians by event/revision, producing one summary per selected event. It retains
source hashes, settings, units and synthetic labels.

In this mode, `--vars '{"top_n": 1}'` cannot override a revision's saved N. Changing
N means preparing and selecting a different revision. Missing, non-integer or
non-positive saved N produces no summary and fails the context check. Conflicting
contexts for one event are also refused. No selection means zero summaries, with
no fallback to the original export. A broken selection still fails the selector's
own reconciliation test. All-rejected selections retain counts and null metrics.

The [eight integration unit cases](../dbt/models/selected_analysis_unit_tests.yml)
cover correction B, saved N versus a CLI override, separate events/distances,
missing weather, no selection, rejected-only input and invalid/ambiguous settings.
Expected correction B: five candidates, three finishers, median and top-N median
6,600 seconds (312.84 seconds/km), weather coverage 2/3. A separate synthetic
10 km event tests N=2, a 6,000-second top-N median and 1/3 coverage. These cases
all passed in the [native selected-mode build](#verified-selected-revision-run).

Default mode retains the original seven unit cases. Selected mode enables twelve
selector cases plus eight integration cases. Local checks parsed both modes with
network connections blocked and checked rendered GoogleSQL syntax and lineage;
they did not execute SQL. The original source mode remains the default.

<a id="next-native-check"></a>
### Verified selected-revision run

On 9 September 2026, the existing private views in
`runwx-learning-mifuha.runwx_dbt_demo`, `europe-west1`, passed the selected-input
validation. The [evidence JSON](evidence/selected-analysis-validation.json) records
all executed tests, full read-back rows, hashes, SQL definitions, image IDs,
invocation IDs and query usage.

| Build | Unit tests | Data tests | Views |
| --- | --- | --- | --- |
| Original mode | 7 passed | 14 passed | 3 built |
| First selected build | 13 passed, 1 error, 6 skipped | 10 passed, 5 skipped | 2 built, 2 skipped |
| Corrected selected build | 20 passed | 15 passed | 4 built |

The error was in an expected fixture row: `duration_s` and `weather_match_status`
appeared in a different order from the other rows. dbt generated a positional
`UNION ALL`, and BigQuery rejected the incompatible types. Reordering those two
keys fixed the test. Model SQL and expected values did not change. This is why
successful offline parsing was not sufficient execution evidence.

All eight integration tests passed: selected staging retains every candidate and
saved N; the fact keeps the unmatched finisher; correction B ignores a CLI N
override; two events keep separate counts/distances/N; empty selection gives no
summary; rejected-only input keeps quality counts; invalid N and conflicting
revisions produce no summary. The twelve selector cases also passed, including
retry/replay, invalid receipts, duplicate keys and incomplete candidates.

The first verification query compared every staging/fact/summary field with
original A. The second compared selected rows plus staging/fact/summary with
correction B. Both matched the saved Python baselines after normalising equivalent
UTC spellings and accepting numeric precision within relative `1e-12` / absolute
`1e-9`. Source hashes, revision/code identity and saved N matched explicitly.

| Selected summary | Value |
| --- | --- |
| Candidates / accepted / skipped / invalid | 5 / 3 / 1 / 1 |
| Finishers | 3 |
| Median / top-N median duration | 6,600 / 6,600 seconds |
| Median / top-N median pace | 312.84 / 312.84 seconds per kilometre |
| Requested / effective N | 20 / 3 |
| Weather matched / unmatched | 2 / 1 |
| Weather coverage | 2/3, partial |

This remains a synthetic correction demonstration, not a historical comparison.
Successful selected invocation: `f6eab51a-b0e7-40b7-9d05-fea60d89d44c`.

Used **3 dbt builds and 2 verification queries**. The 156 recorded query jobs
include dbt's internal schema probes: 155 succeeded and 1 failed. Reported usage
was **160,954 bytes processed** and **1,247,805,440 bytes billed**
(1,190 MiB). Billed bytes are not a verified currency charge after allowances or
trial credits. Every job recorded the 300-second and 100 MiB limits; dbt used
one thread and no automatic query retries.

Input rows, schemas and modification timestamps stayed unchanged, including the
revision metadata, receipts and selection pointer. The selector definition was
unchanged; all four deployed definitions match the final compiled SQL. One empty
schema-probe table from the failed test remains with its automatic expiry at
`2026-09-10T03:48:34Z` (04:48 BST); it contains zero rows and zero bytes. No manual
cloud cleanup was performed.

The deployed chain uses `--vars '{"enable_revision_preview": true}'`.
Keep that flag when rebuilding it; a default-mode build deliberately returns the
three analytical views to the original single-export input. View replacement is
still not atomic: the failed build updated selector/staging before stopping, and
the corrective build completed the chain. No orchestration or recovery protocol
was added. Python tests, Terraform checks, GitHub CI and other platforms were not
rerun for this SQL-fixture correction and documentation update.

## Local setup and checks

From the repository root, use a separate environment so dbt's dependencies do not
change the report environment. The commands below use WSL/Linux/macOS paths:

```bash
python3 -m venv .venv-dbt
.venv-dbt/bin/python -m pip install -r dbt/requirements.txt
.venv-dbt/bin/dbt --no-partial-parse parse \
  --project-dir dbt --profiles-dir dbt --target local
```

On Windows use `.venv-dbt/Scripts/python.exe` and `.venv-dbt/Scripts/dbt.exe`.
Installation may need internet access. [profiles.yml](../dbt/profiles.yml) defaults
to a local target with dummy project identifiers. Parsing checks the project and
unit-test definitions without cloud credentials. The manifest appears under
`dbt/target/`, with logs under `dbt/logs/`.

The [container](../dbt/Dockerfile) provides the same dbt entry point. Building may
need internet access; its complete [dependency lock](../dbt/requirements.lock)
keeps the validated package versions. The parsing command disables networking:

```bash
docker build -t runwx-dbt:local dbt
docker run --rm --network none --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=256m runwx-dbt:local \
  --no-partial-parse parse \
  --profiles-dir . --target local
```

This container writes artifacts under `/tmp`, which disappears after this command.
Offline parsing checks project wiring, **not SQL execution**.
`compile --no-introspect` with `--no-populate-cache` renders SQL without warehouse
introspection, but this adapter still initialises credentials. Compilation needs
existing ADC; parsing does not. Neither command runs the SQL tests.
To parse the selected input and its tests, add
`--vars '{"enable_revision_preview": true}'` to either parsing command above.
This changes the input of the three analytical models as well as enabling the selector.

Native dbt unit tests and data tests execute in BigQuery, even when the fixtures
are saved locally. Unit tests use short-lived schema-probe tables in the output
dataset; dbt drops them after a normal run, with a 12-hour expiry as a fallback. See the [compile reference](https://docs.getdbt.com/reference/commands/compile)
and [unit-test reference](https://docs.getdbt.com/docs/build/unit-tests).

## Cloud execution

[dbt.tf](../infra/gcp/dbt.tf) prepares one private `runwx_dbt_demo` dataset in
`europe-west1`; `enable_dbt_demo` defaults to false. Terraform owns the dataset;
dbt owns its three views. The existing input table remains unchanged.

The verified execution used the local container with the `cloud` profile
and existing Application Default Credentials mounted read-only.
Run that container as the host UID/GID so it can read the restrictive ADC file
and write artifacts to the mounted output directory.
It requires no service-account key, image publication or Cloud Run changes.
The profile uses one thread, no job retries, a 300-second query wait and a
100 MiB billed-byte limit per query. The byte limit is not an account spending cap.

For the deployed selected chain, include `--vars '{"enable_revision_preview": true}'`.
Run one container `dbt build`, retain its `manifest.json`, `run_results.json`,
compiled SQL and logs in a mounted local output directory, then retrieve the mart
and compare its counts, medians, pace, hashes and settings with the Python baseline.
Record BigQuery job identifiers and usage separately from analytical values.
A first build, one corrected rerun if needed, and three verification queries are
estimated below $0.10 for this tiny input at current [BigQuery pricing](https://cloud.google.com/bigquery/pricing).
This estimate excludes existing project resources and is not a spending cap.

## Verified cloud run

Project `runwx-learning-mifuha`, private dataset `runwx_dbt_demo`, location
`europe-west1`. The [evidence JSON](evidence/dbt-first-build.json) records full
example rows and column types for each view, every executed test, all query job
IDs, image IDs, source hashes, settings and comparisons.

The first build stopped at its first unit test because a SQL fixture used
`FLOAT` instead of GoogleSQL's `FLOAT64`. No views were created by that attempt.
The first read-only verification query also found two row-count tests using
`WHERE` without `FROM`. Those test SQL statements were corrected; model SQL,
metrics and expected analytical results did not change.

The corrected SQL preflight matched all seven cases and returned no failures
from fourteen data checks. The second container build then passed **7 native
unit tests, 14 data tests and 3 view models**, with no skips, in 33.56 seconds.
Successful dbt invocation: `f903eb19-8b5a-4196-9209-81508df436f0`.

| Kind | Executed test | Result |
| --- | --- | --- |
| Unit | `staging_keeps_every_candidate_and_flattens_weather` | pass |
| Data | `accepted_values_stg_race_results_validation_status__accepted__skipped__invalid` | pass |
| Data | `accepted_values_stg_race_results_weather_match_status__matched__unmatched__not_applicable` | pass |
| Data | `not_null_stg_race_results_source_row_id` | pass |
| Data | `not_null_stg_race_results_validation_status` | pass |
| Data | `not_null_stg_race_results_weather_match_status` | pass |
| Data | `row_outcomes_are_consistent` | pass |
| Data | `single_export_context` | pass |
| Data | `staging_reconciles_source` | pass |
| Data | `unique_stg_race_results_source_row_id` | pass |
| Unit | `fact_keeps_equal_finishers_distinct` | pass |
| Unit | `fact_keeps_accepted_finisher_without_weather` | pass |
| Data | `accepted_fact_reconciles` | pass |
| Data | `not_null_fct_race_results_pace_s_per_km` | pass |
| Data | `not_null_fct_race_results_source_row_id` | pass |
| Data | `unique_fct_race_results_source_row_id` | pass |
| Unit | `summary_matches_python_demo_and_clamps_n` | pass |
| Unit | `top_two_uses_even_median_of_fastest_finishers` | pass |
| Unit | `mixed_settings_do_not_produce_a_blended_summary` | pass |
| Unit | `rejected_only_export_has_no_invented_metrics` | pass |
| Data | `event_summary_reconciles` | pass |

The final read-back compared every field of five source rows, five staging rows,
three fact rows and one summary row with the local baseline. All agreed after
normalising equivalent UTC timestamp spellings; integral JSON numbers may omit
`.0`. The summary also agreed with the earlier direct SQL execution. A separate
read-only N=1 calculation kept three finishers and 2/3 coverage while changing
the top-N median to 3,600 seconds. The saved view still uses N=20.

| Measured usage | Result |
| --- | --- |
| dbt builds / separate verification queries | 2 / 3 |
| Query jobs, including dbt internal work | 36: 34 successful, 2 failed |
| Reported bytes processed | 15,868 |
| Reported bytes billed | 167,772,160 (160 MiB) |
| Jobs without byte statistics | 2 failed jobs |

Billed bytes include query minimums and are **not a verified currency charge**
after allowances or credits. Every job's configuration recorded the 100 MiB
limit. The source table and its modification timestamp were unchanged, only the
three intended views remain, and no temporary test tables remain. Terraform's
final plan found no changes. No additional Cloud Run execution was needed.

Inspect the [summary view in BigQuery](https://console.cloud.google.com/bigquery?project=runwx-learning-mifuha&p=runwx-learning-mifuha&d=runwx_dbt_demo&t=mart_event_summary&page=table).
The saved full row is also in the evidence JSON, so reading it needs no new query.
Python tests were not rerun for these SQL-fixture/test corrections; application
code was unchanged. GitHub CI and other platforms were not tested in this run.

## Failure and reproducibility

A dbt build is not an atomic publication: a failed test does not restore earlier
view definitions. The raw source stays intact, but some views may already have
changed. Inspect the failing test and saved artifacts before rerunning.
The container pins dbt Core, its adapter and indirect dependencies through the
[image lock](../dbt/requirements.lock). The local environment command above installs
only the direct pins; use the container for the fixed dependency set. Retain image
identifiers as execution evidence; see [dependency updates](container.md#dependency-updates).
The [local revision/attempt/selection contract](revisions.md) is tested in Python.
The [optional warehouse selector](warehouse-revisions.md) is separately validated
in BigQuery, as is the guarded writer's update/rollback path. The local input
switch above connects it to these views and has passed native validation. Existing receipts attest to candidate validation, not to every later
version of analytical SQL. Keep the dbt invocation and model definitions as
separate execution evidence. Recovery across execution attempts remains later work.

Historical analysis still needs a suitable second edition and checked course,
distance and timing comparability. See [architecture](architecture.md).
