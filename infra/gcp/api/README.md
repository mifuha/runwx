# Public API Terraform root

This separate root owns only the read-only API identity, its exact BigQuery table
grants and the public Cloud Run service. It does not own the existing project,
enabled APIs, Artifact Registry repository, BigQuery datasets or dbt views.

Use an immutable image digest from the existing `runwx/runwx-api` repository:

```bash
terraform init
terraform plan \
  -var='project_id=runwx-learning-mifuha' \
  -var='image_uri=europe-west1-docker.pkg.dev/runwx-learning-mifuha/runwx/runwx-api@sha256:...'
```

Review a complete plan before applying. After deployment, check `/health` and
compare all configured public course responses with the saved analytical results.

The 22 September 2026 deployment updated the existing service's image and health
probes. Both course responses matched, and Terraform then reported no remaining
changes. See the [deployment record](../../../docs/evidence/public-api-validation.json).

The later GNR deployment added read grants for its summary table and comparison
view and updated only the existing service's image. All three course responses
passed validation, and the
post-apply plan was no-op. See the [GNR deployment record](../../../docs/evidence/gnr-public-api-validation.json).

The process-only health endpoint is `/health`. Cloud Run's
[known issues](https://docs.cloud.google.com/run/docs/known-issues) document conflicts
with some public paths ending in `z`, so the service and container probes avoid those
paths.

The Battersea change adds table-level read grants for its 13 snapshots, 39 dbt
edition views and one comparison view. The saved real-digest plan has 53 additions,
one update to the existing service image and no deletions. The image is published
by digest; the grants and image are not deployed yet.
