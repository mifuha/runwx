# Architecture

## Historical analysis implemented today

The current output covers [five Lydd editions](../README.md#real-historical-comparison)
with 1,197 finishers, three Folkestone editions with 1,215 finishers, 19 sampled
Great North Run editions and 18 full-field Battersea Park 10K editions with 2,725
finishers. With 16 Berlin research editions, the live site covers **five courses
and 61 editions**. It uses fixed race snapshots and real hourly ERA5 weather. Python
prepares the inputs; BigQuery and dbt produce the staging, accepted-results fact,
edition summary and comparison models. Historical builds have run from local
containers; the same export and dbt code has also run in separate Cloud Run jobs
for Folkestone 2019.

Berlin's separate research mart is also verified: 16 editions from 2003–2018 and
541,730 accepted records. Its opt-in dbt build produces a materialized summary,
with independent reconciliation. This is a separate opt-in build; the shared
stage runner handles the edition/comparison sequence described below. The API,
trends, table and scatter plot are live.
It preserves captured populations, unknown timing and fixed-window weather rather
than treating the records as verified official fields. See [Berlin statistics](berlin-statistics.md).

```mermaid
flowchart TD
    inputs["Saved race + ERA5 inputs<br/>local files or Cloud Storage"] --> export["Python validation/export<br/>local or Cloud Run report job"]
    export --> artifacts["Audit report + result rows<br/>local files or Cloud Storage"]
    artifacts --> loader["Validate export, load or verify"]
    loader --> snapshot[("BigQuery snapshot tables")]
    snapshot --> runner["dbt builds + tests"]
    runner --> edition["Edition models + tests"]
    edition --> comparison["Comparison views + stored summaries<br/>and tests"]
    comparison --> checks["Independent reconciliation"]
    comparison --> api["Read-only Cloud Run API"]
    api --> pages["Trends, scatter plots + tables<br/>How it works page"]
    runner --> evidence["Retained success/failure evidence"]
    api -. "HTTPS /health" .-> monitoring["Cloud Monitoring<br/>API availability + dbt failure alerts"]
    runner -. "Cloud Run dbt failure" .-> logs["Cloud Logging"]
    logs --> monitoring
```

[Source qualification](historical-inputs.md) checks race date/start, timing fields,
row counts, course evidence and weather provenance before an edition is admitted.
Captured source bytes remain unchanged. For 2025, an explicit derived snapshot
retains the 261 complete, provider-reconciled rows; its own hash and mapping back
to the original 399-row capture preserve provenance. The 138 excluded rows are
verified incomplete companions, not a generic deduplication rule. Source-specific
capture and reconciliation remain manual.
New raw captures and per-runner exports stay outside Git; public evidence records
hashes, settings, aggregate results, validation outcomes and limitations.

For full-field sources, the [row exporter](result-export.md) reads and hashes the
same saved bytes, assigns each candidate a snapshot row ID, records its validation outcome and aligns weather
to an estimated run midpoint. Weather matching uses aware UTC timestamps, a maximum
30-minute gap by default and the earlier observation for an equal-distance tie.
Unmatched finishers remain in performance statistics. GNR and Berlin use fixed
edition-level weather windows instead; they do not infer individual starts or
runner weather matches.

The [BigQuery loader](bigquery-staging.md) validates the complete export and expected
hash before submission. A pre-created table receives one export using `WRITE_EMPTY`
and `CREATE_NEVER`. Full typed-row readback must match before success is reported;
an identical sequential rerun verifies existing data without another upload.
Changed or extra rows fail verification and are not overwritten.

## Availability and data checks

Cloud Monitoring checks the public API’s `/health` response from three locations
every five minutes. Sustained failures in at least two locations trigger an email;
recovery sends a closing notification. The dashboard shows requests, errors and
latency. These checks do not query BigQuery or prove the comparison data is correct.
The dbt tests, reconciliation and retained execution evidence cover that boundary.

A controlled test on 14 October 2026 verified an opening incident, recovery and
cleanup. Both emails were confirmed received on 15 October. The test used shorter
timing and left the production service and monitoring unchanged. See the
[monitoring test and troubleshooting guide](../infra/gcp/monitoring/README.md#verified-alert-test).

The Cloud Run dbt job has a separate enabled log-based failure alert. Its wrapper
records a structured error and still fails the job; Monitoring sends the email.
It covers caught dbt exceptions, while export, loading and failures before Python
starts remain outside its scope. Refreshes are manual.

On 26 October 2026, a marked configuration failure produced an incident and a
confirmed email before any dbt or BigQuery work. The temporary test policy was
removed, then the operational policy was enabled. See the
[verified failure example and response steps](pipeline-alerts.md#verified-cloud-test).

## Fixed snapshot boundaries

The minimum guarantees are exact snapshot identity/provenance, duplicate-safe
sequential reruns, validation before successful output and distinguishable
deliberate corrections. Row identity combines event identity, the race-file hash
and candidate position; it identifies a source row, not an athlete. Weather hashes
and interpretation settings accompany the export. A corrected export uses a
separate source table and output dataset, preserving the earlier snapshot.

Analyses name their input datasets explicitly. There is no automatic current
revision pointer. Guarded selection, concurrent publication and elaborate receipt
handling remain a separate learning spike; adoption needs a concrete changing-data
or concurrent-writer requirement. The loader assumes controlled sequential use.

The [historical Terraform root](../infra/gcp/historical/README.md) owns only the
chosen snapshot tables and their dbt output datasets. It references the existing
staging dataset and uses separate state from the original cloud demo and parked
experiment. Existing resources/state are preserved; a generic apply of the original
root is not part of the historical workflow. Source tables have no automatic expiry.

<a id="planned-dbt-models"></a>
## dbt models and validation

Each full-field snapshot has three views. The comparison defaults to a logical
view in an explicitly chosen output dataset; two ephemeral input models assemble
SQL over the selected editions. Battersea now stores only its final comparison
as an 18-row table. Its edition models remain views. Views retain query logic;
the stored table retains results and needs an explicit rebuild after input changes.
The [Battersea serving checks](battersea-serving.md) explain the measured benefit
and refresh trade-off. Berlin already uses a stored research summary.

| Model | What one row represents | Main checks |
| --- | --- | --- |
| `stg_race_results` | One candidate source row, with flattened settings/weather. | Unique row identity; source reconciliation; consistent validation outcomes. |
| `fct_race_results` | One accepted candidate, with duration and pace. | Accepted count matches staging; finishers without weather remain present. |
| `mart_event_summary` | One complete race/weather/settings context and chosen top-N setting. | Exact median and fastest-N median; quality totals; coverage denominator; one context. |
| `mart_course_comparison` | One explicitly chosen edition dataset, relative to a named baseline. | One summary/output per dataset; matching fact context/counts; baseline cardinality. |

The default [edition graph](dbt-models.md) has 21 tests. It rejects empty or mixed
input contexts instead of emitting a blended summary. An all-rejected export still
reports quality counts with null performance metrics. Requested/effective N remain
visible, and fastest-N is a median of the fastest N finishers.

The [comparison](historical-comparison.md) adds seven tests and exposes mean/median
pace, exact p25/p75, fastest-N median, matched-weather medians and separate pace/
speed changes. Incompatible course, distance or interpretation settings retain raw
statistics with a status and null differences. Different N suppresses only fastest-N
differences. SQL checks do not establish that two physical routes are identical.

The initial 2022/2024 native builds passed 42 tests; the 2023/2026 expansion passed
49. The latest 2025 addition passed 28 tests across its edition build and the
five-edition comparison. Readbacks matched the 37-field new mart and all 62 fields
in each comparison row. [2025 execution evidence](evidence/lydd-2025-validation.json)
separates cached fixture tests, uncached data checks and query usage; the
[previous expansion](evidence/historical-edition-expansion-validation.json) is retained.
CI runs offline Python, container, Terraform and dbt parse checks; it does not
execute warehouse SQL.

## Offline Berlin case study

The [Berlin case study](https://runwx-api-f6n35ol7sa-ew.a.run.app/case-studies/berlin)
checks the pattern within recorded female and male groups, compares the fastest
captured results with the rest, and leaves out each edition in turn.

```mermaid
flowchart TD
    inputs["Saved Berlin + ERA5 inputs"] --> study["Offline Python analysis<br/>+ independent checks"]
    study --> aggregates["Checked aggregate CSV + JSON"]
    aggregates --> page["Static charts + tables<br/>served by the existing Cloud Run API"]
```

The [method and code](../analysis/berlin/README.md) reuse the existing parser and
weather validation. The page is built from checked aggregates and packaged with
the service. It makes no warehouse query or calculation when opened. These are
edition-level associations, not evidence of individual heat effects.

<a id="planned--next-milestone-warehouse-analysis"></a>
## Cloud Run validation/export path

The [deployed Cloud Run Job](first-cloud-run.md) runs the existing report and result-
export functions through one small coordinator. Its stored defaults remain **fully
synthetic**. An execution-specific Folkestone 2019 run produced 459 accepted results,
459 weather matches and a byte-identical copy of the frozen warehouse-input NDJSON.
The job does not load BigQuery or invoke dbt.

```mermaid
flowchart TD
    inputs[("Private Cloud Storage<br/>approved fixed inputs")] --> job["Cloud Run validation/export job"]
    job --> reports[("Audit report JSON<br/>private Cloud Storage")]
    job --> exports[("Result-row NDJSON<br/>private Cloud Storage")]
    reports --> loader["Check exact generations<br/>then use the safe loader"]
    exports --> loader
    loader --> snapshot[("Explicit BigQuery snapshot")]
```

Input generations and SHA-256 checks bind the downloaded bytes. Execution-specific
object names and create-only uploads retain earlier successful artifacts. NDJSON is
written first and the report envelope last as the pair's completeness marker; a
consumer must require both. The runtime service account can read four exact input
objects and create output objects; it has
no BigQuery loader/dbt permissions. A separate least-privilege build identity can
read Cloud Build source archives, push this repository's image and write build logs.

This verifies real fixed input through the deployed parsing/export boundary. The
exact Folkestone 2019 artifact pair was also read through the manual Storage adapter
and fully matched its existing protected BigQuery snapshot twice, without another
load. This validation/export job still does not load BigQuery or invoke dbt. The dbt
stage is a separate Cloud Run job with its own runtime identity and permissions.
A separate Cloud Run service serves the [public comparison page](https://runwx-api-f6n35ol7sa-ew.a.run.app/)
and read-only API. It reads the existing comparison marts; the statistics stay in
dbt. The live service now covers five Lydd, three Folkestone, 19 sampled Great
North Run, 18 full-field Battersea and 16 Berlin research editions. GNR uses the
fastest 1,000 available running results per edition and fixed start-area weather context.
Battersea keeps separate race dates for multiple editions in the same year.
The API also serves the live [How it works page](https://runwx-api-f6n35ol7sa-ew.a.run.app/how-it-works).
The [API documentation](api.md) links the deployment checks. Inputs are still
captured and historical runs started manually. The Airflow DAG completed a
Folkestone run in Composer; that environment was removed after validation.

The verified downstream boundary is a thin Storage adapter: it requires exact
report/export generations, verifies the report-last completeness marker and fully
prepares the downloaded NDJSON before delegating to the existing BigQuery loader.
The adapter does not load directly from a Storage URI, create warehouse resources or
choose a destination. Because the target already contained byte-identical rows, the
safe result was `already_present_verified`; no duplicate table or load was needed.
See the [native validation record](evidence/cloud-export-bigquery-validation.json).

The dbt job reuses the same stage runner, locked image, models, tests and
reconciliation code used locally:

```text
dbt stage runner
  → edition build
  → comparison build
  → independent reconciliation
  → immutable evidence
```

A failed stage stops the next stage, although BigQuery views created before a later
failure may remain. Successful and failed executions retain a create-only archive
and completion record. Execution `runwx-dbt-wwjgk` completed the Folkestone 2019
edition build, the three-edition comparison build and independent reconciliation;
its immutable evidence was downloaded and verified. See the
[dbt stage contract](dbt-models.md#cloud-run-dbt-stage).

## Offline entry points and interpretation limits

The [runnable demo](../README.md#runnable-offline-demo--synthetic-weather) uses saved
Lydd 2022 results with **synthetic weather**. The same report runs locally or in a
[container](container.md). Its v1 JSON contains input hashes and settings, but has
no historical-provider/timing qualification; the historical export and companion
provenance records supply that context separately. The
[CSV/SQLite workflow](development.md#csv-and-sqlite-workflow) remains available.
Domain rules, use cases and external I/O follow the existing
[package layers](development.md#package-structure-and-api).

The Lydd comparison uses a common 21,097 m pace convention and an explicit unchanged-
course assumption supported by venue/certificate evidence. Provider distances are
retained separately. Full-field midpoint matching uses the event start; individual
starts are unavailable. ERA5 is a venue proxy, not measured personal exposure.
GNR uses a fixed 10:00–14:00 Europe/London start-area window; Berlin uses
09:00–15:00 Europe/Berlin at the finish area. Those windows are independent of
finishing durations. Their precipitation is a window total.

Every course has a separate temperature–pace scatter using existing summary
values. Battersea dots show full dates; GNR retains its top-1,000 label, and small
cohorts carry a caution. The plots do not pool populations, fit a trend or claim
that weather caused a pace change.
