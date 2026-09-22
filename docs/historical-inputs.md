# Fixed historical inputs for BigQuery and dbt

The exporter and loader accept saved historical race results with historical
reanalysis weather. Preparation is local; it does not create cloud resources or
upload data. The Lydd 2022 and 2024 snapshots have also completed the approved
BigQuery load and dbt path; the measured results are below.

## Prepare one explicitly chosen snapshot

Use the saved race input and derived weather CSV, with their exact hashes and
source references. Preserve the original weather response, request parameters,
provider/model, units and capture time alongside the CSV. An export hashes the
bytes it parses; the companion provenance record connects the CSV to its raw
source. Labels are supplied interpretations, not automatic source verification.

```bash
python -m runwx export-results \
  --race-html /path/to/saved-race.html --weather-csv /path/to/weather.csv \
  --course-id chosen-course --distance-m 21097 --timezone Europe/London \
  --race-kind historical --weather-kind historical_reanalysis \
  --timing-basis chip > /path/to/results.ndjson

python -m runwx.bigquery_load \
  --input /path/to/results.ndjson \
  --table project-id.runwx_staging.chosen_snapshot \
  --expected-sha256 REVIEWED_EXPORT_SHA256
```

Choose distance and timing interpretation from the selected sources; the values
above illustrate the flags. `--timing-basis` describes the existing `Time` column;
it does not switch columns for Eventrac. A frozen Sporthive JSON bundle instead uses
`--race-input /path/to/snapshot.json --race-format sporthive_json` and requires the
timing flag to select its chip or gun field. The bundle retains the provider race
metadata, all ordered result pages and their response hashes, plus explicit event
time/location metadata from retained evidence. Sporthive fractions are rounded up
to match the whole-second convention used by the published results.
For a source already rounded to whole seconds, document its upstream rounding
separately. Omit the flag when the timing basis remains unknown.

The loader requires explicit supported source kinds, one snapshot/settings context,
and the exact reviewed export hash. Unknown labels or mixed contexts fail locally.
It keeps the same schema, deterministic load job identity, `WRITE_EMPTY` and exact
readback comparison: an identical sequential rerun is a no-op, and conflicting
data fails without overwrite. A deliberately corrected race file has a different
hash and source-row identities; give its export a separate destination table.
Changed weather or settings also require a separate export table, even though
the underlying race-row identities remain unchanged.

## Bind existing models to that export

The logical source `race_results` points to one chosen physical table. Models
still process one complete export per invocation. Preserve each edition's views
in a distinct output dataset; reusing an output dataset would replace its views.

```bash
RUNWX_DBT_DATASET=runwx_dbt_chosen_snapshot \
  .venv-dbt/bin/dbt --no-partial-parse parse \
  --project-dir dbt --profiles-dir dbt --target local \
  --vars '{"source_dataset": "runwx_staging", "source_table": "chosen_snapshot"}'
```

The local target uses a dummy project and needs no credentials. Parsing checks
source/model wiring, not SQL correctness or BigQuery contents. With no overrides,
the existing synthetic table and demo output dataset remain the defaults.
Actual table/dataset creation, upload and `dbt build` are separate cloud operations.
See the [loader](bigquery-staging.md) and [dbt execution](dbt-models.md) instructions.

## Same-course comparison

The relevant requirement is the same route and distance across editions, with
consistent timing interpretation. Matching the official half-marathon distance
is not required to compare elapsed durations or percentage changes. If both
editions use the same distance denominator, percentage pace change equals
percentage duration change. Exact metres still affect the absolute seconds/km
label; retain any disputed distance as an explicit convention.

Record the evidence for route equivalence and any remaining assumption. A shared
course ID alone does not establish that the route was unchanged. Weather provides
context for a difference; two editions with different fields of runners do not
isolate a causal weather effect. Keep coverage and source limitations visible.

## 2025 source qualification

The original organiser capture contains 399 rows but 261 distinct finishing
positions. The complete 261 rows match all names, chip durations and gun durations
on 27 saved timing-provider pages. Each of the remaining 138 rows is an incomplete
companion of a complete result, with the same chip time but missing fields.

An explicit selection produces a 261-row **derived analysis snapshot**. The
original capture is unchanged; the derived file has its own SHA-256 and a mapping
from every derived row back to its original candidate row. Serialization may
normalize HTML formatting; retained cells, parsed results and event metadata were
checked equal. This source-specific selection introduces no general deduplication
or revision mechanism. The database uses the derived snapshot's row identity.

Weather was captured as 24 hourly ERA5 observations for 9 March 2025. The 09:00
Europe/London start is 09:00 UTC; all 261 finishers have a matched observation.
The [2025 validation record](evidence/lydd-2025-validation.json) includes original,
derived and export hashes, qualification counts and native execution results.
Raw captures, the row mapping, athlete names and runner-level exports stay local.

## Executed historical comparison

The initial 2022/2024 execution below is preserved as the first warehouse milestone.
The comparison has since expanded to **2022–2026**, with **1,197 finishers** and
full weather coverage. The latest 261-row 2025 addition passed exact loader
readback, a duplicate-safe rerun, its edition build and the five-edition comparison.
See the [current comparison](historical-comparison.md#current-validation-status),
[2025 execution evidence](evidence/lydd-2025-validation.json) and retained
[2023/2026 expansion evidence](evidence/historical-edition-expansion-validation.json).
The existing ingestion schema and metric models were sufficient.

On 10 September 2026, the Python loader and local dbt container processed both
fixed snapshots against BigQuery in `europe-west1`. Each snapshot has its own
source table and output dataset. Both initial loads passed full row readback;
both sequential reruns returned `already_present_verified` without another upload.
Each dbt build created three views and passed 14 data tests plus seven unit tests.
Nine fixture unit-test queries reused BigQuery cached results; all 28 tests on
the real snapshot data ran uncached.
Two additional queries reconciled the mart fields and matched-weather medians
with the saved Python baselines. This real-data execution used local invocation;
it did not run through Cloud Run or an orchestrator.

| Metric | Lydd 2022 | Lydd 2024 |
| --- | ---: | ---: |
| Accepted finishers | 189 | 229 |
| Median chip duration | 1:55:54 | 1:58:26 |
| Median pace, common 21,097 m convention | 5:29.6/km | 5:36.8/km |
| Fastest 20 finishers' median duration | 1:22:33.5 | 1:25:22 |
| Weather coverage | 189/189 | 229/229 |
| Matched temperature median | 5.8 °C | 8.8 °C |
| Matched wind-speed median | 7.34 m/s | 2.08 m/s |
| Matched precipitation median | 0 mm | 0.5 mm |
| Matched humidity median | 61% | 90% |

The 2024 median duration was 152 seconds (2.19%) longer; the fastest-20 median was
3.40% longer. Percentage pace changes are identical because both use the same
distance denominator. The timing provider reports 21,082 m; 21,097 m is the retained
analysis convention, not a newly verified course measurement. Shared certificate
and venue references support the explicit assumption of an unchanged route.

These weather values are medians across results matched to hourly ERA5 reanalysis
at a venue proxy. Alignment uses each estimated run midpoint and the event start;
individual start offsets and route conditions are unavailable. The different
runner fields and two editions do not establish that weather caused the difference.

All 74 jobs succeeded: two loads and 72 query jobs, including dbt's temporary
schema probes. Every query had a 100 MiB maximum billed-bytes limit; aggregate
billed query volume was 340 MiB. Source tables occupy 224,250 logical bytes.
Temporary probe tables were absent at the final metadata check. The saved
Terraform plan added four resources without changing or deleting existing ones;
its separate state preserves the earlier demo and parked experiments.

The [execution evidence](evidence/historical-warehouse-validation.json) records
source/export hashes, code/image identity, load job IDs, dbt invocation IDs,
reconciliation values and measured usage. At the quoted starting rate, the query
volume corresponds to about US$0.002 before free allowances at the
[published starting rate](https://cloud.google.com/bigquery/pricing); this is not an invoice
charge or a measurement of remaining trial credit. Retained storage continues.

The optional [multi-edition comparison view](historical-comparison.md) adds baseline
differences, mean pace and the middle-50% pace range. Its initial BigQuery validation
passed all seven comparison tests and an uncached readback matched both output
rows. That separate execution record preserves the initial test syntax
error, the corrected test and the successful focused follow-up.
