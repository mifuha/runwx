resource "google_service_account" "dbt_runtime" {
  count        = var.enable_dbt_stage ? 1 : 0
  account_id   = "runwx-dbt"
  display_name = "runwx dbt job: build and reconcile approved historical datasets"
  depends_on   = [google_project_service.required]
}

resource "google_project_iam_member" "dbt_job_user" {
  count   = var.enable_dbt_stage ? 1 : 0
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.dbt_runtime[0].email}"
}

resource "google_storage_bucket_iam_member" "dbt_evidence_creator" {
  count  = var.enable_dbt_stage ? 1 : 0
  bucket = google_storage_bucket.reports.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.dbt_runtime[0].email}"
  condition {
    title      = "Only new dbt execution evidence"
    expression = "resource.name.startsWith(${jsonencode("projects/_/buckets/${google_storage_bucket.reports.name}/objects/dbt-runs/")})"
  }
}

resource "google_cloud_run_v2_job" "dbt" {
  count               = var.enable_dbt_stage ? 1 : 0
  name                = "runwx-dbt"
  location            = var.region
  deletion_protection = true

  template {
    task_count  = 1
    parallelism = 1
    template {
      service_account = google_service_account.dbt_runtime[0].email
      timeout         = "1800s"
      max_retries     = 0
      containers {
        image   = var.dbt_image_uri
        command = ["python", "cloud_stage.py"]
        resources {
          limits = { cpu = "1", memory = "1Gi" }
        }
        dynamic "env" {
          for_each = {
            RUNWX_DBT_CONFIG        = jsonencode(var.dbt_stage_config)
            RUNWX_DBT_EXPECTATIONS  = jsonencode(var.dbt_stage_expectations)
            RUNWX_DBT_OUTPUT_PREFIX = "gs://${google_storage_bucket.reports.name}/dbt-runs"
            RUNWX_IMAGE             = var.dbt_image_uri
          }
          content {
            name  = env.key
            value = env.value
          }
        }
      }
    }
  }

  lifecycle {
    precondition {
      condition     = var.dbt_image_uri != null && var.dbt_stage_config != null && var.dbt_stage_expectations != null
      error_message = "The enabled dbt stage requires an immutable image, configuration and expectations."
    }
    precondition {
      condition = (
        var.dbt_image_uri == null ? true :
        startswith(var.dbt_image_uri, "${var.region}-docker.pkg.dev/${var.project_id}/runwx/runwx-dbt@sha256:")
      )
      error_message = "The dbt stage image must use this project's runwx/runwx-dbt repository path."
    }
    precondition {
      condition = (
        var.dbt_stage_config == null ? true :
        var.dbt_stage_config.project == var.project_id && var.dbt_stage_config.location == var.region
      )
      error_message = "The dbt stage project and location must match this Terraform root."
    }
    precondition {
      condition = (
        !var.enable_dbt_stage ? true :
        var.enable_bigquery_staging && var.dbt_stage_config != null &&
        var.dbt_stage_config.source_dataset == "runwx_staging"
      )
      error_message = "The dbt stage requires the parent root's runwx_staging dataset."
    }
  }

  depends_on = [
    google_project_iam_member.dbt_job_user,
    google_storage_bucket_iam_member.dbt_evidence_creator,
  ]
}
