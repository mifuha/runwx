# Separate state. Never import the parent or historical resources into this root.
locals {
  data_project = "runwx-learning-mifuha"
  region       = "europe-west1"
  reports      = "${local.data_project}-runwx-reports"
  member       = "serviceAccount:${google_service_account.orchestrator.email}"
}

resource "google_project_service" "composer" {
  project            = var.orchestration_project_id
  service            = "composer.googleapis.com"
  disable_on_destroy = false
}

resource "google_service_account" "orchestrator" {
  project      = var.orchestration_project_id
  account_id   = "runwx-orchestrator"
  display_name = "Temporary runwx Airflow coordinator"
}

resource "google_project_iam_member" "composer_worker" {
  project = var.orchestration_project_id
  role    = "roles/composer.worker"
  member  = local.member
}

resource "google_storage_bucket" "environment" {
  project                     = var.orchestration_project_id
  name                        = "${var.orchestration_project_id}-airflow"
  location                    = local.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  # Disposable deployment/log bucket only. Retained runwx buckets are untouched.
  soft_delete_policy { retention_duration_seconds = 0 }
}

resource "google_project_iam_custom_role" "invoke_job" {
  project     = local.data_project
  role_id     = "runwxOrchestratorJob"
  title       = "runwx invoke and inspect jobs"
  permissions = ["run.jobs.get", "run.jobs.run", "run.jobs.runWithOverrides", "run.executions.get"]
}

resource "google_cloud_run_v2_job_iam_member" "invoke" {
  for_each = toset(["runwx-report", "runwx-dbt"])
  project  = local.data_project
  location = local.region
  name     = each.value
  role     = google_project_iam_custom_role.invoke_job.name
  member   = local.member
}

# Operations are regional resources, not children of a job's IAM policy.
# Only reads, but project-wide: do not claim an unverified region IAM condition.
resource "google_project_iam_custom_role" "poll_operation" {
  project     = local.data_project
  role_id     = "runwxOrchestratorPoll"
  title       = "runwx read Cloud Run operation status"
  permissions = ["run.operations.get"]
}

resource "google_project_iam_member" "poll_operation" {
  project = local.data_project
  role    = google_project_iam_custom_role.poll_operation.name
  member  = local.member
}

resource "google_project_iam_custom_role" "read_artifact" {
  project     = local.data_project
  role_id     = "runwxOrchestratorArtifact"
  title       = "runwx read exact artifact objects"
  permissions = ["storage.objects.get"]
}

resource "google_storage_bucket_iam_member" "read_artifact" {
  bucket = local.reports
  role   = google_project_iam_custom_role.read_artifact.name
  member = local.member
  condition {
    title = "Read report and dbt evidence only"
    expression = join(" || ", [for prefix in ["reports/", "dbt-runs/"] :
      "resource.name.startsWith(${jsonencode("projects/_/buckets/${local.reports}/objects/${prefix}")})"
    ])
  }
}

resource "google_project_iam_member" "query_job" {
  project = local.data_project
  role    = "roles/bigquery.jobUser"
  member  = local.member
}

resource "google_bigquery_table_iam_member" "snapshot_reader" {
  project    = local.data_project
  dataset_id = "runwx_staging"
  table_id   = "folkestone_2019_f95b3ae312e3"
  role       = "roles/bigquery.dataViewer"
  member     = local.member
}

resource "google_composer_environment" "experiment" {
  project         = var.orchestration_project_id
  name            = "runwx-airflow-experiment"
  region          = local.region
  deletion_policy = "DELETE"
  labels          = { project = "runwx", purpose = "supervised-experiment" }
  storage_config { bucket = google_storage_bucket.environment.name }
  config {
    environment_size = "ENVIRONMENT_SIZE_SMALL"
    resilience_mode  = "STANDARD_RESILIENCE"
    node_config { service_account = google_service_account.orchestrator.email }
    software_config {
      image_version = var.composer_image
      pypi_packages = var.pypi_packages
      airflow_config_overrides = {
        "core-dags_are_paused_at_creation" = "True"
        "core-dag_ignore_file_syntax"      = "regexp"
      }
    }
    workloads_config {
      scheduler {
        cpu        = 0.5
        memory_gb  = 2
        storage_gb = 1
        count      = 1
      }
      dag_processor {
        cpu        = 1
        memory_gb  = 2
        storage_gb = 1
        count      = 1
      }
      web_server {
        cpu        = 1
        memory_gb  = 2
        storage_gb = 1
      }
      worker {
        cpu        = 1
        memory_gb  = 2
        storage_gb = 1
        min_count  = 1
        max_count  = 1
      }
      triggerer {
        cpu       = 0.5
        memory_gb = 1
        count     = 0
      }
    }
  }
  depends_on = [google_project_service.composer, google_project_iam_member.composer_worker,
    google_cloud_run_v2_job_iam_member.invoke, google_project_iam_member.poll_operation,
    google_storage_bucket_iam_member.read_artifact, google_project_iam_member.query_job,
  google_bigquery_table_iam_member.snapshot_reader]
}

output "dag_gcs_prefix" {
  value = google_composer_environment.experiment.config[0].dag_gcs_prefix
}

output "runtime_identity" {
  value = google_service_account.orchestrator.email
}
