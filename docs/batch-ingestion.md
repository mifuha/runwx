# GNR batch preparation and loading

Use one configuration to prepare several saved GNR editions and load or verify
their snapshots. The command calls the existing sample exporter and BigQuery
loader, then runs the existing GNR models and independent reconciliation when
`analytics` is configured. Lydd and Folkestone keep their existing commands.
Source discovery, table provisioning and public API deployment remain separate.

Start with [the example configuration](../batches/gnr.example.json). Its paths are
placeholders: point them at your qualified saved inputs. Paths are relative to the
configuration file. Each edition needs the race JSON, category JSON, ERA5 response
and retained weather request. The race and category capture records default to
`<input>.capture.json`; use `race_capture` and `categories_capture` for other paths.
The records must match the input hashes, byte counts and edition source URLs.

The [reviewed edition catalog](../src/runwx/adapters/races/gnr_editions.json) supplies
the event ID and date. A new year with the same source contract needs a reviewed
catalog entry and one configuration entry, with saved course/date evidence. A
new format or course still needs qualification; configuration cannot waive it.

The `analytics` settings name the dbt output dataset and baseline year. The edition
list is the **complete comparison membership**, including the baseline; all of its
snapshots must pass before the summary and comparison build. The example uses its
own output dataset, not the live 19-edition mart. Omit `analytics` for loading only.
Partial load selection is not part of this version.
`maximum_bytes_billed` defaults to 100 MiB per dbt query. The existing 19-edition
build needed a higher cap; set an explicit reviewed value in `analytics` for that
batch. An inherited environment setting cannot silently raise this configured cap.

```bash
python -m runwx batch prepare batches/gnr.example.json \
  --output data/local/prepared/gnr
```

Preparation is offline. It checks every requested edition and writes deterministic
NDJSON, `plan.json`, its checksum and `preparation.json`. If any edition fails,
the summary lists the errors and no executable plan or exports are written.
Use a new output directory each time.

The plan records each destination, source hashes, export hash, schema, timing
counts and planned load job ID. Dates and event IDs come from the reviewed catalog;
hashes come from verified files and capture records. Table names default to
`gnr_<year>_<first 12 race SHA-256 characters>`, preserving the existing snapshots.
The export hash identifies the complete exported content, including weather and
settings. A deliberately corrected snapshot must name a new `table_id`, using the
same year/12-hex suffix format; for example, use the corrected export hash as the
suffix. The command never replaces conflicting existing rows.

Preparation does not check live table existence. Its destination list is not a
complete Terraform configuration. If resources are needed, preserve the existing
historical root's complete snapshot/IAM mappings when preparing a saved resource
plan. Provision missing tables through that reviewed plan before loading.

After reviewing the destinations and authorising the bounded cloud execution:

```bash
python -m runwx batch execute data/local/prepared/gnr/plan.json \
  --output data/local/executions/gnr-01 \
  --dbt-project dbt --dbt-python .venv-dbt/bin/python
```

Execution needs the `bigquery` extra and existing Application Default Credentials.
For analytics, the separate Python executable needs the locked dependencies in
`dbt/requirements.lock`. Its existing credentials must permit the named output
dataset and source tables. The batch process uses the installed `runwx` package.
It rechecks the configuration, catalog, schema, every input/capture record and
export before requesting credentials or submitting any load. The plan checksum
detects accidental edits; it is not a signature or an approval system. Changed
inputs or settings require a fresh preparation.

The loader processes editions sequentially using its existing `CREATE_NEVER`,
`WRITE_EMPTY` and full typed-row comparison. An identical rerun checks warehouse
contents and reports `already_present_verified`; it does not append data or trust
an earlier local status. A conflict or failed operation stops later editions and
returns a failing exit status. Successful earlier loads remain.

`execution.json` records per-edition status, elapsed time, planned load IDs, returned
verification job IDs and failure details. The planned ID is saved before submission.
After a timeout, inspect that job and the destination before rerunning into a new
execution directory. The shared loader reuses its deterministic job ID and checks
existing rows; the batch command adds no automatic retry or checkpoint engine.

With analytics configured, the shared dbt runner builds the all-edition summary
once, then the comparison once. Each build checks its model/test artifacts before
the next starts. Independent Python calculations from the validated exports are
compared with bounded BigQuery readbacks of both marts. Sample counts, timing
basis, weather context, source hashes, pace distributions and baseline differences
must match. Evidence includes each stage's status, artifacts and reconciliation
query IDs. A failed stage stops downstream work; already-created tables or views
are not rolled back. Loading alone reports `analytical_status: not_run`.

The [GNR Airflow DAG](airflow.md#gnr-batches) calls these same preparation, loading,
build and reconciliation functions as separate tasks. Its offline test uses real
Airflow execution with synthetic inputs and simulated dbt/BigQuery boundaries.
It is not a live Composer or native SQL validation of the new batch runner.
