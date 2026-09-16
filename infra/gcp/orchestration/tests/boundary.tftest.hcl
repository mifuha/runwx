mock_provider "google" {}

variables {
  orchestration_project_id = "runwx-orchestration-example"
  composer_image           = "composer-3-airflow-3.1.7-build.10"
}

run "separate_project_and_narrow_access" {
  command = plan
  assert {
    condition     = google_project_iam_member.composer_worker.project != google_project_iam_member.query_job.project
    error_message = "Composer Worker must never be granted in the data project."
  }
  assert {
    condition     = toset(keys(google_cloud_run_v2_job_iam_member.invoke)) == toset(["runwx-report", "runwx-dbt"])
    error_message = "Invocation must remain scoped to the two existing jobs."
  }
  assert {
    condition     = google_bigquery_table_iam_member.snapshot_reader.role == "roles/bigquery.dataViewer" && google_bigquery_table_iam_member.snapshot_reader.table_id == "folkestone_2019_f95b3ae312e3"
    error_message = "The first experiment only verifies the existing Folkestone table."
  }
  assert {
    condition     = google_composer_environment.experiment.config[0].workloads_config[0].worker[0].max_count == 1 && !google_storage_bucket.environment.force_destroy
    error_message = "Keep one worker and require explicit bucket cleanup."
  }
}

run "reject_data_project" {
  command = plan
  variables { orchestration_project_id = "runwx-learning-mifuha" }
  expect_failures = [var.orchestration_project_id]
}

run "reject_floating_image" {
  command = plan
  variables { composer_image = "composer-3-airflow-3" }
  expect_failures = [var.composer_image]
}

run "reject_airflow_override" {
  command = plan
  variables { pypi_packages = { Apache_Airflow = "==3.1.6" } }
  expect_failures = [var.pypi_packages]
}
