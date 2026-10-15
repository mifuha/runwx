# API availability monitoring

This root manages one dashboard, one HTTPS uptime check, one alert policy and
one email channel for the existing `runwx-api` service. They were deployed on
14 October 2026, and the follow-up Terraform plan reported no changes.
It uses its own Terraform state and does not manage the API, IAM or warehouse.

## What it checks

Google's public checkers call `/health` every five minutes from three locations.
A pass needs a valid TLS certificate, HTTP 200 and JSON `status: "ok"` within ten
seconds. This checks that the HTTP process can respond. It does not query BigQuery
or prove that the comparison data is correct.

The JSONPath matcher needs a JSON value, so the Terraform configuration uses
`jsonencode("ok")` for the expected string. An unencoded `ok` was rejected during
the first deployment; a regression test now checks that the value decodes correctly.

The alert counts failing locations. More than one must fail continuously for the
ten-minute retest window before an incident opens. One failing location does not
trigger it. Sampling and metric delivery add to detection time. Missing probe
data does not open an incident; a closed incident alone is not proof of recovery.
Check fresh passing probes. Email notifications cover opening and closing an
incident, without repeat reminders.

The dashboard shows request counts by status class, 5xx errors and p95 latency
for each metric series. It links to API error logs. Traffic is low, so latency
samples are sparse and empty charts do not prove zero errors. Health probes count
as requests and can keep an instance warm. Comparison failures such as `503` are
visible in the dashboard/logs but do not have a second alert policy here.

Pipeline checks remain in the existing [dbt execution evidence](../../../docs/dbt-models.md).
This does not add automatic pipeline monitoring or restart Composer.

## Prepare and review

Use the existing developer Application Default Credentials. The operator needs
permission to manage Monitoring dashboards, uptime checks, alert policies and
notification channels in `runwx-learning-mifuha`. This root grants no permissions.
Google's public checkers need no service account on the public endpoint, and the
API runtime service account keeps its existing permissions.

From the repository root:

```bash
cp infra/gcp/monitoring/terraform.tfvars.example infra/gcp/monitoring/terraform.tfvars
# Set the approved email in that ignored file.
terraform -chdir=infra/gcp/monitoring init -lockfile=readonly
terraform -chdir=infra/gcp/monitoring validate
terraform -chdir=infra/gcp/monitoring test
terraform -chdir=infra/gcp/monitoring plan -out=monitoring.tfplan
terraform -chdir=infra/gcp/monitoring show monitoring.tfplan
```

The first saved plan should contain exactly four additions and no changes or
deletions. Review it before approval to apply. The email is marked sensitive, but
Terraform still stores it in local plans and state. Keep those files and any plan
JSON private. The ignored state belongs to this root; preserve it for updates and
removal. Do not copy state from the API root.

After approval, apply the reviewed saved plan. Check that all three locations pass,
inspect the dashboard, confirm the email channel is usable and save a no-op plan.
Future notification tests should use a separately approved, controlled test target.
Do not break the public service to test an alert. Offline Terraform tests check
configuration boundaries; they do not prove live alert timing or email delivery.

## Verified alert test

On 14 October 2026, a temporary check deliberately expected the wrong JSON value
from the healthy `/health` endpoint. A temporary policy reused the existing email
channel. The incident opened at 18:18:41 UK time. After correcting the expected
value, all three locations passed and the incident closed at 18:25:34. The recipient
confirmed receipt of both TEST emails on 15 October; inbox delivery was confirmed
by the recipient, not independently inspected.

The test checked every minute with a two-minute retest window. Production remains
at five-minute checks and a ten-minute window, so this proves the notification and
recovery path, not the production timer. Both temporary resources were removed and
independently confirmed absent. The production check and policy were unchanged,
public health returned 200, and the saved Terraform plan showed no changes.
Private plans, state and logs are retained locally; they are not published here.

## When an alert arrives

1. Open the incident and check which locations failed and when. Open `/health`
   and the comparison page to see what is currently affected.
2. Check the dashboard’s errors and latency, then follow its API error-log link.
   Compare the failure time with recent Cloud Run revisions. A healthy `/health`
   response does not rule out a comparison request failing with `503`.
3. If the comparison fails, inspect the API error and relevant BigQuery job before
   deciding what to fix. Use the retained dbt tests and reconciliation evidence
   for questions about data; do not rerun ingestion just because an alert arrived.
4. After recovery, confirm fresh passing probes from all three locations, the
   closed incident and the recovery email. A closed incident alone is insufficient.
   If an email is missing, check spam and the configured notification channel.

Record the incident, cause if known, action and recovery evidence. Avoid guessing
a cause from a single chart.

## Cost and removal

Three checks every five minutes produce about 25,920 executions in 30 days. That
fits within the current one-million-execution monthly project allowance, assuming
other checks do not use it up. Native Google Cloud metrics are non-chargeable.
Cloud Run requests/compute and log storage still follow their own pricing, and
these probes may reduce scale-to-zero time. No recurring BigQuery query is added.
Check actual usage after deployment; this is not a promise of a zero cloud bill.
See [Google's pricing](https://cloud.google.com/products/observability/pricing),
checked on 14 October 2026.

To remove only this monitoring setup, first prepare and review:

```bash
terraform -chdir=infra/gcp/monitoring plan -destroy -out=monitoring-destroy.tfplan
terraform -chdir=infra/gcp/monitoring show monitoring-destroy.tfplan
```

Only after removal approval, apply that saved destroy plan. It should delete these
four monitoring resources and leave the API and data alone. Terraform removes the
dependent alert policy before its check/channel; the channel refuses forced
deletion if another policy has started using it.

## Documentation checked

The Google Terraform provider documents
[uptime checks](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/monitoring_uptime_check_config),
[alert policies](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/monitoring_alert_policy)
and [dashboards](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/monitoring_dashboard).
These fields were checked against this repository's locked provider, 7.46.1.
Google documents [checker locations](https://docs.cloud.google.com/monitoring/uptime-checks)
and [uptime alerting](https://docs.cloud.google.com/monitoring/uptime-checks/uptime-alerting-policies).
Its [response validation guidance](https://docs.cloud.google.com/monitoring/uptime-checks/response-validation)
explains the JSON value encoding.
