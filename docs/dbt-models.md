# First dbt models

Status: **executed and verified in BigQuery on 8 September 2026**. The source is
the [verified synthetic export](bigquery-staging.md) in
`runwx_staging.synthetic_results`. All three views and all 21 dbt tests passed
in the corrected container build. See the [execution evidence](#verified-cloud-run).

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
finishers as its denominator. Source hashes, event/distance, input-kind labels and
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
The release uses explicitly chosen fixed snapshots; stronger publication and
concurrency controls are deferred until a concrete workflow requires them.

Historical analysis still needs a suitable second edition and checked course,
distance and timing comparability. See [architecture](architecture.md).

For explicitly chosen historical inputs, `source('runwx', 'race_results')` maps
to `source_dataset`/`source_table` variables, defaulting to the existing
`runwx_staging.synthetic_results` table. `RUNWX_DBT_DATASET` selects the output
dataset, defaulting to `runwx_dbt_demo`. Run each snapshot into its own output
dataset to retain both sets of views. The single-export checks and all metric
definitions are unchanged. See [historical input preparation](historical-inputs.md).

## Staged build runner

The [stage runner](../dbt/stage_runner.py) invokes the existing dbt project with
explicit source, edition output, comparison output, comparison inputs, baseline and
`top_n` settings. It uses the locked dbt environment; it adds no metric definitions.
The [example configuration](../dbt/stage-config.example.json) uses placeholder IDs.
The [example expectations](../dbt/stage-expectations.example.json) show the required
shape only; they are not real analytical values. Replace both files with reviewed
resources and frozen expected rows before execution.

Preview validates configuration and prints both commands without invoking dbt,
requesting credentials or creating an execution directory:

```bash
python3 dbt/stage_runner.py \
  --config dbt/stage-config.example.json \
  --expectations dbt/stage-expectations.example.json \
  --output-dir /tmp/runwx-dbt-example
```

With a reviewed configuration, run in the existing dbt environment:

```bash
.venv-dbt/bin/python dbt/stage_runner.py \
  --config /path/to/reviewed-config.json \
  --expectations /path/to/frozen-expectations.json \
  --output-dir /path/to/new-execution-directory \
  --execute
```

The runner builds edition models/tests first, and invokes the comparison selection
only after successful process exit and verification of the edition artifacts.
`edition/` and `comparison/` each retain `target/manifest.json`,
`target/run_results.json`, dbt logs and `console.log`. A new output directory is
required, so rerunning cannot overwrite earlier execution evidence. Both output
datasets may be the freshly built edition's dataset, as in the existing workflow;
the runner rejects comparison writes into another input edition's dataset.

The verifier requires matching artifact invocation IDs, exactly the expected model
and test results, and successful statuses for every result. The current project
contract is three edition models, 14 data tests and seven unit tests, followed by
one materialized comparison model, five data tests and two unit tests. Its two
intermediate models are ephemeral. If that contract changes, update the verifier
and its tests deliberately. Each subprocess has a 30-minute timeout; the existing
profile retains one thread, zero job retries, a 300-second query execution timeout
and a 100 MiB query billing cap. These are not a total-run spending cap.

After both builds pass, the runner independently reads the edition mart plus its
weather distribution and the complete comparison mart. The two queries use explicit
project/dataset identifiers, disabled cache and retries, a 30-second submission
timeout, a 300-second server timeout and a 100 MiB maximum each. Their SQL and
SHA-256 identities, job IDs, byte usage, cache/error metadata and actual rows are
retained under `reconciliation/`. A canonical copy and hash of the expectations are
stored at the execution root before dbt starts, so failed builds retain that identity.

Every field and collection shape must match. Finite floating-point values use a
small numerical tolerance, while timezone-aware start timestamps compare as instants.
Comparison rows are matched in deterministic snapshot-dataset order. A mismatch
is saved and fails the invocation without running another query or modifying data.

`execution.json` records `reconciled` only after both builds and both readbacks pass.
Failures retain completed stage summaries and details. A failure preserves available
artifacts and blocks later work; already-created warehouse views are not rolled back.
Inherited `DBT_*` environment overrides are removed for these bounded invocations;
existing authentication environment variables remain available. Direct `dbt`
commands and the image's default entry point remain supported.

The image includes this same runner. An offline container preview uses:

```bash
docker run --rm --network none --read-only --entrypoint python \
  runwx-dbt:local stage_runner.py --config stage-config.example.json \
  --expectations stage-expectations.example.json \
  --output-dir /tmp/runwx-dbt-preview
```

This is local orchestration preparation. No dbt Cloud Run job or IAM grants have
been deployed for it. Uploading the execution directory create-only, attaching the
image digest/source revision and validating a dedicated cloud identity remain
subsequent steps. Native unit/data tests and analytical reconciliation execute in
BigQuery; offline parsing and process-simulation tests do not establish warehouse
correctness.
