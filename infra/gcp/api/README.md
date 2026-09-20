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

Review a complete plan before applying. The first live validation must request both
configured courses and reconcile them with the frozen comparison evidence.
