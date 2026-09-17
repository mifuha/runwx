# First managed Airflow run

This is the proposed boundary for the first live Airflow experiment. It is a
review document, not evidence that the environment or permissions exist. The
experiment uses the merged DAG against the existing Folkestone 2019 snapshot,
then removes the managed Airflow resources on the same day.

## What this proves

The run should prove that Managed Airflow can coordinate the already verified
Cloud Run, Cloud Storage, BigQuery and dbt stages without moving their business
logic into the DAG.

Three manual DAG runs are in scope:

1. An invalid configuration fails in `validate_configuration`, before a Cloud
   Run job or BigQuery query is submitted.
2. The reviewed Folkestone 2019 configuration completes all six tasks and
   reconciles its report, export, existing snapshot and dbt evidence.
3. The same configuration completes again with fresh immutable Cloud Run
   artifacts and `already_present_verified` from the loader. It must not submit
   a BigQuery load job or duplicate rows.

The Folkestone table already contains all 459 rows. This experiment therefore
proves the duplicate-safe verification path, not the first write into an empty
snapshot. A new destination must be a later, separately reviewed run rather than
an artificial table created for this demonstration.

## Managed environment

Use one standard, small Managed Airflow (Cloud Composer 3) environment in a
separate orchestration project. The project ID below is proposed and must be
checked for availability before it appears in a Terraform plan:

| Setting | Proposed value |
|---|---|
| Environment project | `runwx-orchestration-mifuha` |
| Data and job project | existing `runwx-learning-mifuha` |
| Environment | `runwx-airflow-experiment` in `europe-west1` |
| Runtime service account | `runwx-orchestrator@runwx-orchestration-mifuha.iam.gserviceaccount.com` |
| Environment size | `ENVIRONMENT_SIZE_SMALL` |
| Resilience | Standard; this is a short supervised experiment |
| Airflow image | Pin an available Airflow 3 build after the bundle smoke test; current candidate: `composer-3-airflow-3.1.7-build.10` |
| Schedule | Manual only |
| Concurrency and retries | One active run, one active task, zero task retries |
| Lifetime | Delete on the same day, no later than eight hours after creation starts |

The candidate build is close to the locally tested Airflow 3.1.6 runtime. Before
an apply, list the builds actually available in `europe-west1`, pin one exact
build, and run the DAG import and boundary tests against that build. Do not use a
moving version alias.

The managed deployment needs a deterministic DAG bundle containing the DAG,
`runwx_airflow`, `stage_runner.py`, and the imported `runwx` modules. Record every
file hash in a bundle manifest. Use the exact Composer image's preinstalled
package list to derive the smallest dependency overlay; do not install the whole
local Airflow lock into Composer. This packaging and its import smoke test are the
next implementation slice before any environment is created.

## Identities and permissions

The environment runs DAG code as `runwx-orchestrator`. The existing jobs keep
their current identities:

| Work | Identity |
|---|---|
| Airflow scheduling, job invocation, artifact checks and existing-table verification | `runwx-orchestrator` |
| Race parsing, validation, weather alignment and export | existing `runwx-report` |
| dbt builds, tests, queries and evidence upload | existing `runwx-dbt` |
| Terraform apply, DAG upload, trigger and teardown | authorised developer identity |

`runwx-orchestrator` receives the mandatory project-level `roles/composer.worker`
role in `runwx-orchestration-mifuha`. The current role includes broad Storage and
Artifact Registry permissions, so granting it in `runwx-learning-mifuha` would
weaken the existing data and image boundaries. The separate project contains only
the temporary Composer environment and its bucket. The application permissions in
the existing runwx project can then remain narrow.

Add only these pipeline permissions:

| Resource | Grant to `runwx-orchestrator` | Why |
|---|---|---|
| `runwx-report` job | `run.jobs.get`, `run.jobs.run`, `run.jobs.runWithOverrides` | Verify the deployed contract and submit one execution with reviewed settings |
| `runwx-dbt` job | `run.jobs.get`, `run.jobs.run`, `run.jobs.runWithOverrides` | Verify the deployed contract and submit one execution with reviewed settings |
| Executions under the two jobs | `run.executions.get` | Inspect the submitted execution when needed |
| Cloud Run operations in `runwx-learning-mifuha` | `run.operations.get` | Poll the exact submitted operation; project-level read access is a documented limitation |
| Reports bucket objects under `reports/` and `dbt-runs/` | `storage.objects.get` | Pin metadata/generation and download the exact report, NDJSON, manifest and ZIP |
| `runwx-learning-mifuha` project | `roles/bigquery.jobUser` | Submit the bounded verification query |
| `runwx_staging.folkestone_2019_f95b3ae312e3` only | `roles/bigquery.dataViewer` | Inspect schema and compare every stored row with the export |

Implement job permissions with bindings on the two existing jobs and Storage
reads with a condition for the two object prefixes. Keep operation polling in a
separate read-only custom role: region-scoped IAM support has not been verified.
The predefined Cloud Run executor-with-overrides role also grants cancellation,
which the DAG does not use. The orchestrator gets no access to the input bucket,
no Artifact Registry write, no BigQuery data editor, no dbt output-dataset role,
and no ability to change either Cloud Run job.

The empty-table branch of the loader requires write permission. It is deliberately
unavailable here: if the reviewed destination is unexpectedly empty, the task must
fail instead of turning this verification run into an unapproved first load.

The authorised developer identity needs `composer.environments.create/get/update/delete`
in the orchestration project and `iam.serviceAccounts.actAs` on
`runwx-orchestrator` for provisioning. It also needs separately approved permission
to add the reviewed cross-project grants in `runwx-learning-mifuha`. IAM
administration remains a deployment permission and is never attached to the
orchestrator. Managed Airflow Gen 3 does not need the Gen 2
`roles/composer.ServiceAgentV2Ext` grant; do not add it pre-emptively.

If a separate billed project is not acceptable, use local Airflow with the same
narrow runwx permissions for the first live execution. Do not put the managed
environment in `runwx-learning-mifuha` and describe it as least privilege.

## Terraform boundary

Put the experiment in a new `infra/gcp/orchestration` root and state. It targets
the approved empty orchestration project and references the jobs, report bucket
and exact BigQuery table in `runwx-learning-mifuha`, but it must not import or
manage those retained resources. This avoids the parked resources in the parent
state and the retained historical data in the historical state.

Creating the empty project and attaching its billing account is a small bootstrap
action with its own reviewed plan. Do not mix project deletion into the routine
environment destroy plan.

The new state owns only:

- the Composer and Compute API declarations in the approved orchestration project
  with `disable_on_destroy = false`;
- one custom-mode VPC and one `europe-west1` subnet, explicitly selected by Composer,
  with no ingress firewall rules;
- `runwx-orchestrator`, custom roles and additive experiment-only role bindings;
- one regional environment bucket with public access prevention and
  `force_destroy = false`;
- one small standard Composer 3 environment using that bucket and identity.

`force_destroy = false` makes teardown stop if the environment bucket still
contains the DAG, logs or other evidence. The bucket contents are reviewed and
exported before a separate authorised deletion. Destroying this state must not
delete or change the report/dbt jobs, their service accounts, the input/report
buckets, Artifact Registry, or any BigQuery table or dataset.

Review a saved Terraform plan before apply. Its resource actions must contain only
the items above and must have zero deletes. Approval may cover the complete
bounded apply, three-run and teardown window; preparation alone does not authorise it.

## Cost boundary

Managed Airflow is billed for the actual time the environment exists. At review
time, Google's pricing page displays USD 0.06 per DCU-hour and USD 0.000232877 per
GiB-hour of database storage for its default Iowa selection; the database starts
at 10 GiB. Record the selected `europe-west1` SKU price before apply rather than
assuming it is identical. One period in Google's published example uses 12 DCUs.
At the displayed rate, that is about USD 0.72 per hour plus USD 0.0023 per hour for
database storage; 15 DCUs is about USD 0.90 per hour.

Use these experiment limits:

- eight hours maximum from creation request to deletion request;
- USD 10 operational ceiling for Composer, its bucket, monitoring, network and
  the small downstream Cloud Run/BigQuery work together;
- standard resilience and one worker's worth of sequential work;
- no environment snapshot, schedule or unattended overnight period.

At the 12–15 DCU examples, eight hours is about USD 5.78–7.22 before small Storage,
Monitoring, network and downstream charges. This is an estimate, not a hard billing
cap. Billing can arrive late: use elapsed time and the reviewed maximum configured
resources to estimate spend, with the billing view as a later cross-check. If
the projected total can exceed USD 10 or the environment cannot be ready and tested
inside the window, export the available evidence and start teardown. A budget alert
can warn, but it does not enforce this ceiling.

## Run and evidence checklist

Before the first trigger:

- verify the exact Composer image, DAG bundle hash and imported DAG;
- inspect effective IAM for `runwx-orchestrator` and confirm its ADC identity in a
  harmless task log;
- validate that the frozen configuration still names the two immutable Cloud Run
  image digests and the exact Folkestone table;
- confirm the table contains the expected 459 rows and is not empty;
- record the environment creation time and eight-hour teardown deadline.

For each run, retain the DAG run ID, six task states, Cloud Run operation/execution
names, object names/generations/hashes, loader status and query job IDs, and final
dbt evidence identity. A submission timeout is ambiguous: inspect the logged
operation and exact execution before any manual retry. Never clear and resubmit an
invocation task just because its client wait timed out.

Copy the small Airflow run/task metadata and relevant task logs out of the
environment bucket before teardown. The immutable analytical artifacts remain in
the existing reports bucket under their execution-specific names. Record a concise
public result only after the downloaded evidence has been independently checked.

## Teardown

Teardown is part of the experiment, not optional cleanup:

1. Pause triggers and confirm no task or Cloud Run execution is still running.
2. Export the three DAG-run summaries and relevant task logs.
3. Apply a reviewed destroy plan for the Composer environment first.
4. Confirm the managed environment is gone. Composer does not delete its bucket.
5. Review and then delete the experiment bucket contents and bucket within the
   explicitly approved teardown scope.
6. Remove the cross-project IAM bindings, experiment custom roles and
   `runwx-orchestrator` account.
7. Remove the experiment VPC/subnet through this state. Leave the Composer and
   Compute APIs enabled. The auto-created default network and its firewall rules are
   outside this state and require a separately reviewed cleanup action. Detach
   billing only through the reviewed project-bootstrap boundary.
8. Verify that no Composer environment, experiment bucket, runtime grant or paid
   runtime resource remains and that all retained runwx jobs, buckets and BigQuery
   data are unchanged.

Cloud Logging entries can remain under the project's normal retention. Their small
retention cost is recorded as a limitation rather than deleting project-wide logs.

Official references: [Composer Terraform setup](https://cloud.google.com/composer/docs/composer-3/terraform-create-environments),
[Composer access control](https://cloud.google.com/composer/docs/composer-3/access-control),
[Composer Python dependencies](https://cloud.google.com/composer/docs/composer-3/install-python-dependencies),
[Composer pricing](https://cloud.google.com/products/managed-service-for-apache-airflow/pricing),
[Composer deletion](https://cloud.google.com/composer/docs/composer-3/delete-environments),
[Cloud Run job permissions](https://cloud.google.com/run/docs/reference/iam/permissions),
and [BigQuery roles](https://cloud.google.com/bigquery/docs/access-control).
