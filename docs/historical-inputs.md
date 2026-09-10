# Fixed historical inputs for BigQuery and dbt

The exporter and loader accept saved historical race results with historical
reanalysis weather. Preparation is local; it does not create cloud resources or
upload data. The previous cloud execution evidence uses synthetic inputs.

## Prepare one explicitly chosen snapshot

Use the saved race HTML and derived weather CSV, with their exact hashes and
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
it does not switch columns. The parser retains its whole-second conversion.
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
