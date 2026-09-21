locals {
  # The comparison marts are logical views. Their exact nested view/table
  # dependencies must also be readable unless a separate authorized-view layer
  # is introduced. Keep this list aligned with the reviewed API course catalog.
  editions = {
    runwx_dbt_lydd_2022_99783aaa85b8       = "lydd_2022_99783aaa85b8"
    runwx_dbt_lydd_2023_bb1171d02f0f       = "lydd_2023_bb1171d02f0f"
    runwx_dbt_lydd_2024_f0758db89562       = "lydd_2024_f0758db89562"
    runwx_dbt_lydd_2025_6cbb29274bab       = "lydd_2025_6cbb29274bab"
    runwx_dbt_lydd_2026_5243cfebedc2       = "lydd_2026_5243cfebedc2"
    runwx_dbt_folkestone_2019_f95b3ae312e3 = "folkestone_2019_f95b3ae312e3"
    runwx_dbt_folkestone_2022_b7e702b5ec87 = "folkestone_2022_b7e702b5ec87"
    runwx_dbt_folkestone_2023_e56f91f4c1ba = "folkestone_2023_e56f91f4c1ba"
  }

  analysis_dependencies = merge([
    for dataset_id, _ in local.editions : {
      for table_id in ["stg_race_results", "fct_race_results", "mart_event_summary"] :
      "${dataset_id}.${table_id}" => {
        dataset_id = dataset_id
        table_id   = table_id
      }
    }
  ]...)

  staging_dependencies = {
    for _, table_id in local.editions : "runwx_staging.${table_id}" => {
      dataset_id = "runwx_staging"
      table_id   = table_id
    }
  }

  comparison_dependencies = {
    "runwx_dbt_lydd_2022_99783aaa85b8.mart_course_comparison" = {
      dataset_id = "runwx_dbt_lydd_2022_99783aaa85b8"
      table_id   = "mart_course_comparison"
    }
    "runwx_dbt_folkestone_2019_f95b3ae312e3.mart_course_comparison" = {
      dataset_id = "runwx_dbt_folkestone_2019_f95b3ae312e3"
      table_id   = "mart_course_comparison"
    }
  }

  query_dependencies = merge(
    local.analysis_dependencies,
    local.staging_dependencies,
    local.comparison_dependencies,
  )
}

resource "google_service_account" "runtime" {
  account_id   = "runwx-api"
  display_name = "runwx public API: query approved comparison dependencies"
}

resource "google_project_iam_member" "query_job" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_bigquery_table_iam_member" "query_reader" {
  for_each   = local.query_dependencies
  project    = var.project_id
  dataset_id = each.value.dataset_id
  table_id   = each.value.table_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_cloud_run_v2_service" "api" {
  name                 = "runwx-api"
  location             = var.region
  description          = "Public read-only historical race pace and weather comparison"
  ingress              = "INGRESS_TRAFFIC_ALL"
  invoker_iam_disabled = true
  deletion_protection  = true

  template {
    service_account                  = google_service_account.runtime.email
    timeout                          = "60s"
    max_instance_request_concurrency = 8

    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    containers {
      image = var.image_uri

      ports {
        name           = "http1"
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle          = true
        startup_cpu_boost = false
      }

      startup_probe {
        failure_threshold     = 10
        timeout_seconds       = 2
        period_seconds        = 2
        initial_delay_seconds = 0
        http_get {
          path = "/health"
          port = 8080
        }
      }

      liveness_probe {
        failure_threshold     = 3
        timeout_seconds       = 2
        period_seconds        = 30
        initial_delay_seconds = 10
        http_get {
          path = "/health"
          port = 8080
        }
      }
    }
  }

  lifecycle {
    precondition {
      condition = startswith(
        var.image_uri,
        "${var.region}-docker.pkg.dev/${var.project_id}/runwx/runwx-api@sha256:",
      )
      error_message = "The API image must use this project's runwx/runwx-api repository path."
    }
  }

  depends_on = [
    google_project_iam_member.query_job,
    google_bigquery_table_iam_member.query_reader,
  ]
}
