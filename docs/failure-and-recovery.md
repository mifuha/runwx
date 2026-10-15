# What happens when something fails?

runwx checks each stage before reporting success. A failed run can still leave
artifacts or warehouse views, so recovery starts by inspecting what actually
finished. It does not mean rerunning everything.

This summary uses existing evidence. **Cloud** means a recorded execution against
real GCP services. **Offline** means tests with controlled inputs and simulated
external services. No new failure runs were performed for this document.

| Situation | What runwx does | Evidence | What to do next |
| --- | --- | --- | --- |
| Invalid pipeline configuration | Fails validation and blocks downstream tasks. | **Cloud:** the [Composer validation run](evidence/composer-airflow-validation.json) blocked all five downstream tasks and submitted no Cloud Run job. | Correct the configuration before starting a new run. |
| Source bytes or export identity do not match | Rejects the mismatch before that boundary's downstream work. | **Offline:** [input hash tests](../tests/test_cloud_report.py) verify no upload. **Cloud:** an omitted timing setting caused an export hash mismatch and stopped the [Composer run](evidence/composer-airflow-validation.json) before BigQuery and dbt. | Check the saved bytes, hashes and interpretation settings. A deliberate correction needs its own explicit snapshot destination. |
| The same snapshot is submitted again | Reads back the stored rows and verifies them without another load. Conflicting rows are rejected, not overwritten. | **Cloud:** the [Folkestone rerun](evidence/composer-airflow-validation.json) verified 459 existing rows with no load job. **Offline:** [loader tests](../tests/test_bigquery_load.py) cover conflicting rows and a lost load response. | Reuse the same qualified snapshot settings for an identical rerun. Investigate a conflict instead of replacing the table. |
| dbt or independent reconciliation fails | Stops later work and records failure with available artifacts. A successful dbt build alone does not mean reconciliation passed. | **Offline:** [runner tests](../tests/test_dbt_stage_runner.py) cover process failure, failed comparison artifacts and mismatched readback; [cloud wrapper tests](../tests/test_dbt_cloud_stage.py) cover retaining failure evidence. | Read the failed stage's logs and actual results. Fix the cause and use a new execution directory. Already-created views may remain. |
| A comparison request cannot read the warehouse | Returns `503` with a plain error message and `no-store`, without exposing internal details. | **Offline:** [API tests](../tests/test_api_app.py) inject a warehouse failure and check the response. This is not a deliberately induced live warehouse outage. | Inspect API logs and the relevant BigQuery job. `/health` can still return `200` because it only checks the HTTP process. |
| The API fails repeated availability checks | Opens an incident after sustained failures in at least two locations, with opening and closing emails. | **Cloud:** the [controlled alert test](../infra/gcp/monitoring/README.md#verified-alert-test) verified failure, fresh passing probes and incident closure. Both emails were confirmed received by the recipient. | Follow the [alert troubleshooting steps](../infra/gcp/monitoring/README.md#when-an-alert-arrives); confirm recovery with fresh probes as well as the closed incident. |

## Before retrying

A timeout while waiting for Cloud Run does not prove the job stopped. Inspect the
operation and execution first. The [orchestration tests](../orchestration/tests/test_pipeline.py)
check that a failed wait logs the operation and does not submit the job again.
The [Airflow guide](airflow.md) explains the manual recovery boundary.

The pipeline is not a transaction across Cloud Storage, BigQuery and dbt. A failed
second artifact upload can leave the first object; consumers require a complete,
verified pair. A failed warehouse readback does not delete the candidate table.
A failed dbt test does not roll back views. These cases are covered by the
[export tests](../tests/test_cloud_report.py), [loader tests](../tests/test_bigquery_load.py)
and [dbt runner contract](dbt-models.md).

## What this evidence does not prove

- The Composer rerun verified an existing snapshot. It did not demonstrate a fresh
  load in that managed run, automatic retry/backoff or a multi-edition backfill.
  That Composer environment was removed; historical runs are started manually.
- The alert test deliberately mismatched the expected JSON on a healthy endpoint.
  It used one-minute checks and a two-minute retest window. It proved the
  notification/recovery path, not a real outage or the production five-minute
  check interval and ten-minute retest timing.
- Availability monitoring does not check analytical correctness. dbt tests and
  independent reconciliation check warehouse results during a run; they are not
  continuous data-quality alerts.
- Failure evidence is retained when it can be written. Storage failure can prevent
  a complete evidence upload; the job still fails. There is no automatic rollback
  or guarantee that every failed run leaves a complete archive.
