# Local race-result export

`export-results` prints one JSON object per line (NDJSON), ready to inspect as rows.
It uses the existing Eventrac parser, race-to-run conversion and weather matcher.
The summary report and the separate CSV/SQLite activity workflow remain available.

## Run the synthetic example

From the repository root, after [setup and activation](../README.md#quickstart):

```bash
python -m runwx export-results \
  --race-html data/sample_race_synthetic.html \
  --weather-csv data/sample_lydd_weather_synthetic.csv \
  --course-id runwx-synthetic-half --distance-m 21097 \
  --timezone Europe/London --max-gap-min 30 \
  --race-kind synthetic --weather-kind synthetic
```

Execution reads the saved files without network requests. Installation may need
internet access. The command prints to stdout; it does not write a database.

**Both the race and weather here are fabricated. They are not historical evidence.**
The five output rows contain:

| Source row | Validation | Finish duration (s) | Weather match |
| --- | --- | --- | --- |
| 1 | accepted | 3600 | matched |
| 2 | accepted | 7200 | matched |
| 3 | accepted | 14400 | unmatched |
| 4 | skipped | null | not_applicable |
| 5 | invalid | null | not_applicable |

Missing weather does not remove row 3 from race statistics. Coverage is 2 out of
3 accepted results. Skipped and invalid rows have no validated finish duration and
do not enter that denominator.

## What one row means

The grain is **one candidate result row in one saved race snapshot**. The parser
numbers candidate rows from 1 in source order, including skipped and invalid rows.
See the [candidate rules](race-report.md#parser-rules).

`source_row_id` combines provider/event identity, the exact race-file SHA-256 and
the source row number. Identical places or times therefore remain separate rows.
Changing any race-file bytes creates a different snapshot identity, even if the
parsed finish times stay the same. Moving identical files does not change output.

This key identifies neither an athlete across editions nor a complete analysis.
Changing weather or settings keeps the source row key but changes the recorded
weather hash or settings. A future warehouse load must distinguish those analyses;
it must not blindly append every replay and count it as new finishers.

## Export contract, version 1

Every line contains the same fields. JSON `null` means unavailable or inapplicable;
it is never a zero finish time or invented weather observation.

| Fields | Meaning |
| --- | --- |
| `export_schema_version` | Currently `1`; separate from the summary-report schema. |
| `source_row_id`, `source_row_number` | Snapshot row identity and original candidate position. |
| `event_id`, `source`, `source_event_id`, `course_id` | Provider/event identity and normalised course identity. |
| `started_at_utc`, `distance_m` | Interpreted event start and supplied event distance, including on rejected rows. |
| `race_sha256`, `weather_sha256` | Hashes of the exact bytes parsed. Local file paths are omitted. |
| `race_kind`, `weather_kind` | Caller-supplied labels. Race: `synthetic`, `historical`, `unknown`; weather: `synthetic`, `historical_reanalysis`, `unknown`. Both default to `unknown`. |
| `validation_status`, `validation_reason` | `accepted`, `skipped` or `invalid`; reason is null for accepted rows. |
| `place`, `duration_s` | Validated finishing place and whole seconds; both null for rejected rows. |
| `weather_match_status`, `weather_match_reason` | `matched`, `unmatched` or `not_applicable`; unmatched rows include a reason. |
| `weather` | Null, or the matched observation: `observed_at_utc`, `temp_c`, `wind_mps`, `precipitation_mm`, `humidity_pct`. |
| `settings` | `course_id_input`, `timezone_name`, `max_gap_seconds`, `alignment`, `tie_break`, `duration_precision`, `timing_basis`. |

The matcher chooses the nearest observation to the run midpoint within the allowed
gap, breaking ties toward the earlier observation. All runners use the event start.
The export has no top-N setting because it exports every candidate without aggregation.
Top-N selection belongs to the later analytical query.

Page/schema errors, malformed weather and unexpected processing errors fail the
whole export before it prints rows. Expected result-row rejections stay visible.
The complete output is built and serialised in memory before printing.

The exporter does not independently verify timing basis, source completeness or
weather location.
`timing_basis` defaults to null. Supply `--timing-basis chip` or `gun` only after
checking what the source's `Time` column means. This records interpretation; it
does not select a different time column or change durations. These labels and
hashes do not verify source accuracy. Retain provider/request and raw-response
provenance alongside the export; see [historical inputs](historical-inputs.md).
Code/dependency versions and the original start-time text are not captured in this
export. Repeatability assumes the same code and environment; companion provenance
is needed when preparing real historical inputs. The synthetic export has passed a
[first BigQuery load and repeat verification](bigquery-staging.md#verified-cloud-run).

## Where SQLite, BigQuery and dbt fit

- **SQLite** stores the existing [activity workflow](development.md#csv-and-sqlite-workflow)
  in a local database file. This export does not add a second race database there.
- **BigQuery** stores and queries these synthetic race rows in a private cloud
  table. Google manages its infrastructure. See the [BigQuery overview](https://docs.cloud.google.com/bigquery/docs/introduction).
- **dbt** organises SQL models and tests. A model can be a `SELECT` in a `.sql` file;
  dbt has BigQuery execute it to build a view or table. dbt is not where the data is
  stored. See [SQL models](https://docs.getdbt.com/docs/build/sql-models) and
  [data tests](https://docs.getdbt.com/docs/build/data-tests).

The planned sequence is staging → accepted-results fact → event-summary mart.
The fact can calculate `duration_s / (distance_m / 1000.0)` as seconds per kilometre;
the mart will calculate median pace and the median pace of the fastest N finishers.
This preserves the existing top-N median definition. Accepted finishers without
weather stay in the analysis, with coverage reported separately. See the
[model grains and checks](architecture.md#planned-dbt-models).

The [first staging loader](bigquery-staging.md) prepares this export for an empty
BigQuery table and verifies equal rows on reruns. Its first cloud execution passed.
The models and their BigQuery execution tests remain part of the
[next milestone](architecture.md#planned--next-milestone-warehouse-analysis).
They are not implemented by this local export.

## Tests

```bash
python -m pytest -q tests/test_result_export.py
```

The tests block network connections, reconcile the synthetic rows with the existing
report, preserve duplicate finishers, check source identity when inputs move or
change, and distinguish missing weather from invalid results. They also check that
bad inputs or unexpected matching failures produce no partial stdout.
