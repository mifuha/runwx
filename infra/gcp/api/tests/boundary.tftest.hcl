mock_provider "google" {}

variables {
  project_id = "runwx-learning-mifuha"
  image_uri  = "europe-west1-docker.pkg.dev/runwx-learning-mifuha/runwx/runwx-api@sha256:1111111111111111111111111111111111111111111111111111111111111111"
}

run "public_api_has_bounded_runtime_and_exact_reads" {
  command = plan

  assert {
    condition     = google_service_account.runtime.account_id == "runwx-api"
    error_message = "The API must use its dedicated runtime identity."
  }

  assert {
    condition     = google_project_iam_member.query_job.role == "roles/bigquery.jobUser"
    error_message = "The API may create bounded query jobs but must not receive a project-wide data role."
  }

  assert {
    condition = (
      length(google_bigquery_table_iam_member.query_reader) == 34 &&
      alltrue([
        for grant in google_bigquery_table_iam_member.query_reader :
        grant.role == "roles/bigquery.dataViewer" && grant.project == var.project_id
      ])
    )
    error_message = "The API must read only the 34 named tables and views in the two approved mart dependency chains."
  }

  assert {
    condition = (
      google_cloud_run_v2_service.api.invoker_iam_disabled &&
      google_cloud_run_v2_service.api.ingress == "INGRESS_TRAFFIC_ALL"
    )
    error_message = "The API service must be publicly reachable without adding an allUsers IAM binding."
  }

  assert {
    condition = (
      google_cloud_run_v2_service.api.template[0].timeout == "60s" &&
      google_cloud_run_v2_service.api.template[0].max_instance_request_concurrency == 8 &&
      google_cloud_run_v2_service.api.template[0].scaling[0].min_instance_count == 0 &&
      google_cloud_run_v2_service.api.template[0].scaling[0].max_instance_count == 1
    )
    error_message = "Keep the public demo at zero-to-one instances, concurrency 8 and a 60-second request timeout."
  }

  assert {
    condition = (
      google_cloud_run_v2_service.api.template[0].containers[0].startup_probe[0].http_get[0].path == "/health" &&
      google_cloud_run_v2_service.api.template[0].containers[0].liveness_probe[0].http_get[0].path == "/health"
    )
    error_message = "Cloud Run must probe the process-only health endpoint."
  }
}

run "reject_floating_api_image" {
  command = plan
  variables {
    image_uri = "europe-west1-docker.pkg.dev/runwx-learning-mifuha/runwx/runwx-api:latest"
  }
  expect_failures = [var.image_uri]
}

run "reject_wrong_api_repository" {
  command = plan
  variables {
    image_uri = "europe-west1-docker.pkg.dev/runwx-learning-mifuha/runwx/other@sha256:1111111111111111111111111111111111111111111111111111111111111111"
  }
  expect_failures = [google_cloud_run_v2_service.api]
}

run "reject_wrong_data_project" {
  command = plan
  variables {
    project_id = "runwx-other-project"
    image_uri  = "europe-west1-docker.pkg.dev/runwx-other-project/runwx/runwx-api@sha256:1111111111111111111111111111111111111111111111111111111111111111"
  }
  expect_failures = [var.project_id]
}

run "reject_wrong_region" {
  command = plan
  variables {
    region    = "europe-west2"
    image_uri = "europe-west2-docker.pkg.dev/runwx-learning-mifuha/runwx/runwx-api@sha256:1111111111111111111111111111111111111111111111111111111111111111"
  }
  expect_failures = [var.region]
}
