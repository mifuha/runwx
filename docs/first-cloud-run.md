# First cloud input/output run

Status: **deployed and verified on 8 September 2026** (Europe/London).
Two successful cloud executions matched the synthetic local baseline. This proves
the storage and execution path. The [historical BigQuery/dbt flow](architecture.md)
is now verified separately through local invocation; connecting it to Cloud Run
remains to be implemented.

```text
Private input bucket (synthetic race HTML + synthetic weather CSV)
    → download exact object generations; check SHA-256 hashes
    → temporary files → existing build_offline_report()
    → private report bucket: reports/<execution>/task-0-attempt-0.json
```

The container's temporary files disappear after the job. The uploaded JSON stays
in Cloud Storage until deleted. The job needs network access to Google Storage
and authentication, but never fetches race or weather provider data.

## Deployed resources and results

| Resource | Identifier |
| --- | --- |
| Project | `runwx-learning-mifuha` |
| Region | `europe-west1` for storage, registry and job |
| Private input bucket | `runwx-learning-mifuha-runwx-inputs` |
| Private report bucket | `runwx-learning-mifuha-runwx-reports` |
| Artifact Registry repository | `runwx` |
| Runtime service account | `runwx-report@runwx-learning-mifuha.iam.gserviceaccount.com` |
| Cloud Run Job | `runwx-report` |

Deployed image, verified against both execution descriptions and saved reports:

```text
europe-west1-docker.pkg.dev/runwx-learning-mifuha/runwx/runwx@sha256:f90bc8ea97497ca377dec4cbc2e4bfb43cfe4484658e602561039782392475d5
```

This Linux/amd64 manifest belongs to the published `first-run` image index
`sha256:2c8257f6f0f1d79b69ac94ce429736fbf74fa977811a430968fe773ef1e1445c`.
They identify two levels of the same image. All 51 application Python files in the
image matched the checkout before publication. The image was built before the
cloud changes were committed, so its Git revision label identifies the base
checkout; use the verified image digest to identify the deployed code.

| Execution | Result | Start-to-completion time | Output generation |
| --- | --- | ---: | --- |
| `runwx-report-tdjvt` | 1 task succeeded, no retries | 27.510 s | `1788823251294987` |
| `runwx-report-btttr` | 1 task succeeded, no retries | 41.499 s | `1788823418694525` |

Both reports were downloaded from their private locations:

```text
gs://runwx-learning-mifuha-runwx-reports/reports/runwx-report-tdjvt/task-0-attempt-0.json
gs://runwx-learning-mifuha-runwx-reports/reports/runwx-report-btttr/task-0-attempt-0.json
```

Every local report field matched except the two source file paths: hashes,
settings, quality counts, coverage and limitations all agreed. The two cloud
`report` objects were identical. Execution names and output URIs differed in the
surrounding metadata, as expected. Input generations matched the uploaded objects;
the first output's generation and checksums stayed unchanged after the repeat.

**Entirely synthetic demonstration:** 5 candidate rows, 3 accepted, 1 skipped,
1 invalid; weather matched 2 of 3 finishers. Best/median/mean finish durations were
3600/7200/8400 seconds. These are pipeline checks, not historical race findings.

The [job execution page](https://console.cloud.google.com/run/jobs/details/europe-west1/runwx-report/executions?project=runwx-learning-mifuha)
shows status, configuration and logs. The
[report bucket](https://console.cloud.google.com/storage/browser/runwx-learning-mifuha-runwx-reports/reports?project=runwx-learning-mifuha)
and [registry](https://console.cloud.google.com/artifacts/docker/runwx-learning-mifuha/europe-west1/runwx?project=runwx-learning-mifuha)
require access to this private project; they are not public downloads.

## Report contract and failure behaviour

[report_io.py](../src/runwx/adapters/gcs/report_io.py) uses the official
`google-cloud-storage` client to download two objects and call the existing report
function. [cloud_report.py](../src/runwx/cloud_report.py) reads configuration from
environment variables and uses the runtime service account through Application
Default Credentials. No service-account key is needed.

Each download is pinned to the generation returned by its metadata lookup. The
bytes must also match the configured local SHA-256. A missing, changed or invalid
input fails the execution before any report upload.

Output names include execution, task and attempt identifiers. Upload uses
`if_generation_match=0`, so an existing object causes failure instead of replacement.
The runtime also lacks delete/overwrite permission. There is no `latest.json` or
automatic selection of a current report. Failed attempts leave earlier reports
alone. If an upload succeeds but its acknowledgement is lost, inspect that exact
object before rerunning: a failed execution does not prove that no object was saved.
See Google's [generation preconditions](https://docs.cloud.google.com/storage/docs/request-preconditions).

The version 1 envelope contains:

- `report`: the existing summaries, row counts, weather coverage, hashes, settings
  and limitations. Only `sources.race.file` and `sources.weather.file` change from
  local paths to `gs://` source locations.
- `execution`: job, execution, task index, attempt and configured image digest.
  Check the digest against the actual execution description as well.
- `storage`: input URIs/generations and the output URI.

Cloud Run supplies the execution identifiers through its
[documented environment](https://docs.cloud.google.com/run/docs/container-contract).
Image identity is recorded around the report; the original report's limitation
about code/dependency versions remains. The cloud wrapper adds no analytical logic.

## Runtime permissions and configuration

[Terraform](../infra/gcp/main.tf) defines:

- Cloud Run, Cloud Storage, Artifact Registry and IAM API enablements.
- Two private Standard buckets, uniform bucket-level access, enforced public
  access prevention and seven-day soft delete.
- One private Docker registry and one dedicated runtime service account.
- Input Object Viewer restricted by an IAM condition to the two named objects;
  output Object Creator restricted to the report bucket's `reports/` prefix.
- One manual job: one task, parallelism 1, 1 vCPU, 512 MiB memory, a five-minute
  timeout and zero task retries. No scheduler is configured.

The runtime has no project-wide data role, report-read permission or input-write
permission. [Object Creator](https://docs.cloud.google.com/storage/docs/access-control/iam-roles)
cannot read, overwrite or delete objects. Retrieving reports requires separate
Object Viewer access; manual execution can use Cloud Run Invoker on this job.
Deployment permissions are separate from runtime permissions: resource/IAM
administration and permission to act as the runtime service account are needed
for setup, not for processing data.

## Saved inputs

| Input | Bytes | SHA-256 |
| --- | ---: | --- |
| [Synthetic race HTML](../data/sample_race_synthetic.html) | 1044 | `70095c35dc919ed11506924765def09eb6e5590e3feb95ee7f0e8e9dc6f82182` |
| [Synthetic weather CSV](../data/sample_lydd_weather_synthetic.csv) | 187 | `835e03b360af5403540aa1f06a99f164ce30140cc958ea9fdbaef301165ca25f` |

The HTML is fabricated: no runner names, an invalid example source URL, placeholder
coordinates and invented times. The parser labels its format/provider `eventrac`;
that does not establish a real event. The weather CSV is also invented despite
its Lydd filename. Neither input is historical evidence.

## Deployment and comparison

The initial run used Google Cloud CLI 583.0.0, Terraform 1.13.5 and Google provider
7.46.1. Local CLI credentials and Application Default Credentials are needed for
setup. Keep credentials, actual tfvars and Terraform state outside Git.

1. Use a dedicated project with billing configured. Enable Service Usage, Cloud
   Resource Manager, Cloud Billing and Billing Budgets for setup. Project creation,
   billing linkage, these setup APIs and the budget are separate from Terraform.
2. Copy [terraform.tfvars.example](../infra/gcp/terraform.tfvars.example) to local
   `infra/gcp/terraform.tfvars`. Set the project and keep `image_uri = null`.
   Initialise Terraform and review/apply a saved plan for storage, registry and
   identity. This stage does not create or execute a job.
3. Follow the [container instructions](container.md) with tag `runwx:cloud-local`.
   The package includes `google-cloud-storage`. Authenticate Docker for the same
   OS user running it, push the image and record its immutable registry digest.
4. Upload only the two synthetic inputs, using `gcloud storage cp
   --if-generation-match=0`. Record their metadata/generations; this precondition
   prevents overwriting existing objects.
5. Set `image_uri` to the pushed digest reference. Review/apply the job plan;
   creating the job does not execute it.
6. Run twice sequentially, download both reports and compare them with the same
   local baseline. This deployment used two of an operating limit of five manual
   executions; five is not a Cloud Run lifetime quota.

These commands execute an existing cloud job. From the repository root and an
activated Python environment, set `PROJECT` to that job's project ID first:

```bash
REGION=europe-west1
EVIDENCE=$(mktemp -d /tmp/runwx-gcp-evidence.XXXXXX)

python -m runwx report \
  --race-html data/sample_race_synthetic.html \
  --weather-csv data/sample_lydd_weather_synthetic.csv \
  --course-id runwx-synthetic-half --distance-m 21097 \
  --timezone Europe/London --weather-kind synthetic > "$EVIDENCE/local.json"

gcloud run jobs execute runwx-report --project "$PROJECT" --region "$REGION" \
  --wait --format=json > "$EVIDENCE/execution.json"
```

After a successful execution, read its actual `metadata.name` from `execution.json`
into `EXECUTION`, then retrieve and compare:

```bash
REPORT_URI="gs://${PROJECT}-runwx-reports/reports/${EXECUTION}/task-0-attempt-0.json"
gcloud storage cp "$REPORT_URI" "$EVIDENCE/cloud.json"
gcloud storage objects describe "$REPORT_URI" --format=json > "$EVIDENCE/output-object.json"
gcloud run jobs describe runwx-report --project "$PROJECT" --region "$REGION" \
  --format=json > "$EVIDENCE/job.json"
python scripts/compare_cloud_report.py "$EVIDENCE/local.json" "$EVIDENCE/cloud.json"
```

Retain a separate evidence directory for each run. The comparator excludes only
the two source file paths. Check execution IDs, input generations and actual image
references separately. Compare the first output's metadata again after the repeat
so unchanged analytical results do not conceal an overwritten object.

## Costs and retained resources

The two inputs and two reports total **9017 bytes**; Artifact Registry reported
**61.579 MB**. The early monitoring snapshot exposed 60 seconds of billable instance
time, which did not account for both one-minute billing minima. Actual billed
charges were not independently verified; missing cost data does not mean zero cost.

Pricing checked on 7 September 2026, in USD before tax, currency conversion or
free allowances:

| Item | Estimate |
| --- | --- |
| Cloud Run, Belgium | $0.000018/vCPU-second plus $0.000002/GiB-second. At 1 CPU/0.5 GiB, one billed minute is about $0.00114; two minima total about $0.00228 compute. |
| Standard storage, Belgium | $0.02/GiB-month. The 1231 input bytes cost less than $0.000001/month. |
| Storage operations | Regional Class A $0.005/1,000; Class B $0.0004/1,000. |
| Artifact Registry | About $0.10/GiB-month above the shared 0.5 GiB free allowance. |

Sources: [Cloud Run pricing](https://cloud.google.com/run/pricing),
[Storage pricing](https://cloud.google.com/storage/pricing) and
[Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing).
Same-region input/image transfers are free under those pricing rules; report
retrieval to a laptop can incur internet transfer charges. Paid image scanning and
Cloud Build were not enabled for this deployment.

The below-$1 estimate assumes at most five manual executions, one image under
1 GiB, tiny inputs/reports and one month's retention. A project-only £3 monthly
budget alert tracks cost before credits, at 50/90/100% thresholds. Neither the
estimate nor the [budget alert](https://docs.cloud.google.com/billing/docs/how-to/budgets)
is a spending cap.

The job has no idle compute charge, but saved objects/images and any billable logs
remain after it finishes. Soft-deleted objects remain chargeable for seven days.
Terraform prevents bucket/registry destruction and job deletion by default;
buckets also refuse deletion while non-empty. Cleanup must account for those
protections, retained reports, and the separately managed project and budget.

## Verification

Checked on Ubuntu/WSL, 8 September 2026:

- Full Python suite: **148 passed in 1.79s**. Cloud-boundary tests block socket
  connections and use saved synthetic inputs.
- Two local container calls used fake storage with real SDK method signatures,
  network disabled and read-only inputs. They matched the local baseline, and
  `pip check` passed. The two cloud runs then exercised real transport and identity.
- Terraform bootstrap added 10 resources; the job plan added 1. Neither changed
  or destroyed existing resources. Final read-only plan: no changes. Format and
  validation passed; bucket privacy and runtime grants were inspected.
- Both downloaded reports matched the local baseline and actual execution/input
  metadata. The first output remained unchanged after the second execution.
- Baseline SHA-256:
  `fd3872c315cae21fab8b0c0377906a59d01685a359e59c77e1d95b090c461fe5`.
- Not run: full suite inside the image, deliberate live IAM-denial or duplicate
  upload probes, other operating systems, BigQuery or dbt. The denied-operation
  and failed-upload cases are covered locally. Actual billed cost is unverified.

The [main boundary test](../tests/test_cloud_report.py),
`test_saved_report_matches_local_and_repeat_keeps_both_outputs`, supplies saved
bytes through fake storage and runs two execution names. It checks expected row
counts and durations, agreement with the local report and preservation of both
outputs. Separate tests cover changed hashes, failed downloads/parsing and
attempts to overwrite an earlier success.

See [architecture](architecture.md) for the planned result-row and dbt milestone,
and the [report reference](race-report.md) for analytical limitations.
