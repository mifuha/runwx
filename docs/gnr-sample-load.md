# Great North Run sample loading

The saved [GNR export](gnr-sample-export.md) has its own BigQuery schema. One
edition's 1,000 rows go into one explicit snapshot table. The table must already
exist in `europe-west1` with the exact
[`gnr_sample_rows.schema.json`](../src/runwx/adapters/bigquery/gnr_sample_rows.schema.json)
schema. Existing full-result tables and dbt models use a different contract.

Preview a saved export without cloud credentials:

```bash
python -m runwx.bigquery_load \
  --input-format gnr-sample \
  --input saved/gnr-2019.ndjson \
  --table PROJECT.runwx_staging.gnr_2019_RACEHASH \
  --expected-sha256 EXPORT_SHA256
```

The preview checks all 1,000 typed rows, the export hash, edition identity,
sample size and ranks, source locators, timing labels, cutoff, shared ERA5 window
and the absence of extra fields. It reports the schema hash and planned load job
ID. The 19 retained exports each pass this preflight locally. The current files
are about 1.97 MB each; this loader has a 4 MiB cap.

Once the destination table and exact settings have been reviewed and created,
adding `--execute` uses the same safe loader as full-result snapshots. It writes
only to an empty table and then checks every stored row. An identical rerun checks
the table without submitting a second load. A conflicting table fails without
overwrite. The loader never chooses an edition or replaces an existing snapshot.

No GNR BigQuery table, load, dbt model or public result has been created by this
change. The local preflight evidence is in the ignored
`data/local/source-feasibility-20260922/gnr-exports/load-preflight.json` file.
