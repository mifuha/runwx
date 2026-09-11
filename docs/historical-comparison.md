# Comparing fixed historical editions

`mart_course_comparison` puts explicitly chosen edition snapshots into one view,
with one row per input dataset and a stated baseline. It reads the existing
`mart_event_summary` and `fct_race_results` views in each dataset. Two ephemeral
models assemble those inputs; only the final comparison model is materialized.
The original ingestion schema, source rows and edition models are unchanged.

The comparison is optional. With no `comparison_datasets`, the original three
models and 21 tests remain the default. Inputs are existing relations in the target
project, not automatically discovered snapshots. Adding another qualified edition
means explicitly adding its dataset; deliberately corrected snapshots remain
distinguishable by their source hashes and dataset binding.

## Statistics and interpretation

| Statistic | What it contributes |
| --- | --- |
| Whole-field median pace | A central result less affected by a few very slow finishes. |
| Whole-field mean pace | A companion measure that shows the influence of the full field, including its slower tail. |
| Pace p25–p75 | Exact interpolated quartiles describing the middle 50% of finishers. |
| Fastest-N median pace | The existing configured statistic; N defaults to 20, and requested/effective N stay visible. |
| Finishers and row outcomes | The size of the field and whether source rows were excluded. |
| Weather medians and coverage | Matched temperature, wind, precipitation and humidity, with the matched-finisher denominator. |
| Pace and speed changes | Differences against the named baseline, using distinct units and sign conventions. |

All accepted finishers contribute to pace statistics, including those without a
weather match. Only matched observations contribute to weather medians. The
quartiles use BigQuery's exact, interpolated
[`PERCENTILE_CONT`](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/navigation_functions#percentile_cont),
which ignores null values by default. No approximate quantile or weather-adjusted
performance score is introduced.

A fastest-100 average can be added for a specific question, but 100 runners cover
different fractions of the current fields: about 53% of 2022 and 44% of 2024.
Median, mean and quartiles give a more useful initial picture of those whole fields.
Fastest-N comparisons also describe different people, not a matched athlete cohort.

Positive `median_pace_change_pct` means slower; positive
`speed_at_median_duration_change_pct` means faster. Speed is derived as
`3600 / median_pace_s_per_km`, labelled **speed at median duration**, not the median
of each runner's speed. The percentages are reciprocal: doubled seconds/km is
+100% pace and −50% speed. Unrounded numeric fields remain available to consumers.

The same route and distance across editions matter; agreement with official race
distance is not required. Shared IDs alone do not prove unchanged routes. Different
courses, distance conventions, timing bases or interpretation settings retain raw
statistics with an explanatory `comparison_status` and null differences. Empty
fields have no invented metrics. Fastest-N differences are null when requested or
effective N differs; whole-field differences remain available. Weather coverage
remains visible rather than excluding unmatched runners.

## Explicit inputs and baseline

Preview the bindings without credentials or warehouse execution:

```bash
RUNWX_DBT_DATASET=approved_output_dataset \
  .venv-dbt/bin/dbt --no-partial-parse parse \
  --project-dir dbt --profiles-dir dbt --target local \
  --vars '{"comparison_datasets": ["edition_2022", "edition_2024"], "comparison_baseline": "edition_2022"}'
```

Dataset IDs must be unique, and the baseline must be in the explicit list. The
relations are constructed with dbt's quoted
[`api.Relation.create`](https://docs.getdbt.com/reference/dbt-classes#relation).
The ephemeral inputs make the external edition dependencies explicit in this
model's SQL; dbt does not build those external edition views for this invocation.

After approval of exact destinations and execution scope, use the cloud target
with the same variables and **`build --select tag:comparison --fail-fast`**.
That selection builds the comparison and its tests without rerunning the original
edition models. The existing query limits, single thread and no-job-retry settings
apply. The output dataset must already exist. Rebuilding there replaces that
dataset's comparison view with the explicitly supplied input set.

Reconciliation tests require one summary and one output row per chosen dataset,
exact fact/summary snapshot context, distinct finisher identities and matching
finisher/weather counts. A missing or duplicate baseline produces no comparison
rows and fails cardinality validation. An incompatible edition is visible as such;
the view does not certify same-course suitability or a causal weather effect.

## Current validation status

The comparison is verified in BigQuery for **2022–2026**: **1,197 finishers** with
complete weather coverage. The latest addition loaded 261 qualified 2025 results;
its equal-data rerun verified every stored row without another upload. No metric,
schema or loader changes were needed.

| Metric | 2022 | 2023 | 2024 | 2025 | 2026 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Finishers | 189 | 226 | 229 | 261 | 292 |
| Median pace | 5:29.6/km | 5:46.5/km | 5:36.8/km | 5:44.3/km | 5:36.3/km |
| Mean pace | 5:30.8/km | 5:52.3/km | 5:45.4/km | 5:52.5/km | 5:39.0/km |
| Fastest-20 median pace | 3:54.8/km | 4:09.6/km | 4:02.8/km | 4:03.8/km | 3:54.5/km |
| Median pace change versus 2022 | 0% | +5.13% | +2.19% | +4.44% | +2.03% |
| Speed at median duration change | 0% | −4.88% | −2.14% | −4.25% | −1.99% |
| Matched temperature median | 5.8 °C | 11.0 °C | 8.8 °C | 13.4 °C | 7.4 °C |
| Matched wind median | 7.34 m/s | 7.47 m/s | 2.08 m/s | 3.87 m/s | 3.05 m/s |
| Matched precipitation median | 0 mm | 0.1 mm | 0.5 mm | 0 mm | 0 mm |
| Matched humidity median | 61% | 81% | 90% | 58% | 74% |
| Weather coverage | 189/189 | 226/226 | 229/229 | 261/261 | 292/292 |

The [2025 execution record](evidence/lydd-2025-validation.json) records **28 passing
dbt tests**: 21 for the new edition and seven for the comparison. All nine fixture
unit tests used cached results; all 19 data tests, loader readbacks and both
additional reconciliation queries were uncached. The new 37-field mart and weather
summary match the saved expectations, as do all 62 fields in each comparison row.
The four earlier rows also match within the existing numerical tolerance; their
means differ only by floating-point rounding below 3 × 10⁻¹².

All **49 jobs succeeded**: one load and 48 queries, with **420 MiB** of reported
billed query volume. These counters are not an invoice charge or trial-credit
balance. The saved Terraform plan added one source table and one output dataset,
with no changes or deletions to existing managed resources. The four old source
tables and twelve edition views remain unchanged; the comparison was rebuilt with
the five-dataset list. No temporary schema-probe tables remain. The parent Terraform
state/configuration and parked experimental resources are preserved.

The [previous 2023/2026 expansion](evidence/historical-edition-expansion-validation.json)
retains its 49-test, four-edition evidence. Three name discrepancies in those inputs
do not affect reconciled durations; athlete matching and demographics remain
unqualified. The 2025 organiser capture had 399 rows for 261 finishing positions.
All 261 complete rows reconcile with the timing provider; 138 incomplete companions
were explicitly excluded from a derived snapshot. Its own hash and mapping to the
unchanged original capture preserve provenance. This is a reviewed source-specific
selection, not automatic deduplication. See [2025 source qualification](historical-inputs.md#2025-source-qualification).

The common 21097 m convention remains; provider metadata is retained separately
(21082 m for 2023/2025; 21000 m for 2026). Shared venue/certificate evidence supports
the unchanged-course assumption. The 2025 start is 09:00 GMT/UTC; the 2026 start is
09:00 BST/08:00 UTC. Weather uses hourly ERA5 at a venue proxy and estimated run
midpoints; precipitation is a preceding-hour sum rather than whole-race rainfall.
Different runner populations and five editions still do not establish causality.

## Initial two-edition validation

The first comparison was verified against BigQuery for the two fixed Lydd snapshots.
All seven comparison tests have passing results across the initial build and its
focused follow-up. One uncached readback matched all 62 columns in both output rows
against the saved baseline, with the timestamp normalization described below.

The underlying Lydd 2022/2024 exports and edition views have passed the
[historical BigQuery run](historical-inputs.md#executed-historical-comparison).
The new comparison SQL compiles offline. Its compiled SQL, translated to a
temporary local DuckDB for semantic checks, passes synthetic expectations and
reproduces the existing two-edition baseline. Translation is supplementary
evidence; it does not prove BigQuery dialect compatibility.

The new dbt unit tests use SQL fixtures for the ephemeral inputs, following
[dbt's documented pattern](https://docs.getdbt.com/docs/build/unit-tests).
They cover the baseline, pace/speed direction, exact quartiles, partial/no weather,
incompatible timing/course, empty/small fields and a missing baseline. CI parses both
the default and enabled comparison configurations with networking disabled. Native
BigQuery execution is recorded separately from those offline CI checks.

The first native BigQuery build on 10 September created the comparison view and
recorded four passing tests, including both unit tests. It then stopped on a syntax
error in the output-cardinality test: the outer `SELECT` used `WHERE` without a
`FROM`. The corrected test counts rows in a `FROM` subquery and filters that count,
following [BigQuery's query syntax](https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/query-syntax#where_clause).
Local checks verify that zero, one or three rows fail and exactly two rows pass.
The corrected test now also passes natively.

The [native execution record](evidence/historical-comparison-validation.json)
preserves the initial failure and the successful follow-up. Only the corrected test,
two tests marked skipped in the first result artifact, and the output reconciliation
were run afterwards; the view and four recorded passing tests were reused. BigQuery
served the follow-up not-null test from cache; the corrected cardinality test,
uniqueness test and output readback were uncached.

The local readback checker initially rejected the preview's timezone-free timestamp
against BigQuery's explicit UTC timestamp. Both were checked against the earlier
verified warehouse UTC value for the same event, then every captured column was
reconciled locally. No source timestamp or expected value changed, and no extra
query was submitted. This was a checker error, not a changed race timestamp.

Across both invocations and the readback, BigQuery recorded 14 jobs, including the
initial syntax error, and 100 MiB of reported billed query volume. The six original
view definitions and both source tables are unchanged, the comparison view was not
rebuilt, and no temporary probe tables remain. No new upload or Terraform operation
was needed.

The initial verified comparison output was:

| Metric | Lydd 2022 | Lydd 2024 |
| --- | ---: | ---: |
| Finishers | 189 | 229 |
| Median pace | 5:29.6/km | 5:36.8/km |
| Mean pace | 5:30.8/km | 5:45.4/km |
| Middle 50% pace range | 4:43.3–6:15.9/km | 4:59.3–6:23.4/km |
| Fastest-20 median pace | 3:54.8/km | 4:02.8/km |
| Median pace change versus 2022 | 0% | +2.19% |
| Speed at median duration change | 0% | −2.14% |
| Matched temperature median | 5.8 °C | 8.8 °C |
| Matched wind median | 7.34 m/s | 2.08 m/s |
| Matched precipitation median | 0 mm | 0.5 mm |
| Matched humidity median | 61% | 90% |
| Weather coverage | 189/189 | 229/229 |

Both use the common 21,097 m convention and chip timing. Route equivalence remains
an explicit assumption supported by the existing source evidence. ERA5 values are
hourly reanalysis at a venue proxy, matched to estimated run midpoints. The different
runner fields and two editions do not isolate weather's causal contribution.
