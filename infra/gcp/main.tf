# Applying this configuration and uploading inputs both require Miha's approval.
# Enable Service Usage and Cloud Resource Manager first, after that approval.
resource "google_project_service" "required" {
  for_each = toset([
    "run.googleapis.com", "storage.googleapis.com",
    "artifactregistry.googleapis.com", "iam.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

resource "google_storage_bucket" "inputs" {
  name                        = "${var.project_id}-runwx-inputs"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  soft_delete_policy { retention_duration_seconds = 604800 }
  lifecycle { prevent_destroy = true }
  depends_on = [google_project_service.required]
}

resource "google_storage_bucket" "reports" {
  name                        = "${var.project_id}-runwx-reports"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  soft_delete_policy { retention_duration_seconds = 604800 }
  lifecycle { prevent_destroy = true }
  depends_on = [google_project_service.required]
}

resource "google_artifact_registry_repository" "runwx" {
  location      = var.region
  repository_id = "runwx"
  format        = "DOCKER"
  lifecycle { prevent_destroy = true }
  depends_on = [google_project_service.required]
}

resource "google_service_account" "runtime" {
  account_id   = "runwx-report"
  display_name = "runwx report job: read approved inputs and create reports"
  depends_on   = [google_project_service.required]
}

resource "google_storage_bucket_iam_member" "input_reader" {
  bucket = google_storage_bucket.inputs.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.runtime.email}"
  condition {
    title = "Only the two approved input objects"
    expression = join(" || ", [for name in [var.race_object, var.weather_object] :
      "resource.name == ${jsonencode("projects/_/buckets/${google_storage_bucket.inputs.name}/objects/${name}")}"
    ])
  }
}

resource "google_storage_bucket_iam_member" "report_creator" {
  bucket = google_storage_bucket.reports.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.runtime.email}"
  condition {
    title      = "Only new report objects"
    expression = "resource.name.startsWith(${jsonencode("projects/_/buckets/${google_storage_bucket.reports.name}/objects/reports/")})"
  }
}

resource "google_cloud_run_v2_job" "report" {
  count               = var.image_uri == null ? 0 : 1
  name                = "runwx-report"
  location            = var.region
  deletion_protection = true
  template {
    task_count  = 1
    parallelism = 1
    template {
      service_account = google_service_account.runtime.email
      timeout         = "300s"
      max_retries     = 0
      containers {
        image   = var.image_uri
        command = ["python", "-m", "runwx.cloud_report"]
        resources {
          limits = { cpu = "1", memory = "512Mi" }
        }
        dynamic "env" {
          for_each = {
            RUNWX_RACE_URI       = "gs://${google_storage_bucket.inputs.name}/${var.race_object}"
            RUNWX_WEATHER_URI    = "gs://${google_storage_bucket.inputs.name}/${var.weather_object}"
            RUNWX_RACE_SHA256    = var.race_sha256
            RUNWX_WEATHER_SHA256 = var.weather_sha256
            RUNWX_OUTPUT_PREFIX  = "gs://${google_storage_bucket.reports.name}/reports"
            RUNWX_IMAGE          = var.image_uri
            RUNWX_REPORT_SETTINGS = jsonencode({
              course_id     = "runwx-synthetic-half", distance_m = 21097,
              timezone_name = "Europe/London", weather_kind = "synthetic",
              top_n         = 20, max_gap_minutes = 30,
            })
          }
          content {
            name  = env.key
            value = env.value
          }
        }
      }
    }
  }
  depends_on = [google_storage_bucket_iam_member.input_reader, google_storage_bucket_iam_member.report_creator]
}
