mock_provider "google" {}

variables {
  project_id = "runwx-offline-placeholder"
}

run "parked_resources_are_absent_by_default" {
  command = plan
  assert {
    condition = (
      length(google_bigquery_dataset.revision_validation) == 0 &&
      length(google_bigquery_table.revision_validation) == 0
    )
    error_message = "New configurations must not create the parked experiment."
  }
}

run "retain_only_the_existing_protected_experiment" {
  command = plan
  variables {
    enable_revision_validation = true
  }
  assert {
    condition = (
      length(google_bigquery_dataset.revision_validation) == 1 &&
      google_bigquery_dataset.revision_validation[0].dataset_id == "runwx_revision_demo" &&
      google_bigquery_dataset.revision_validation[0].location == "europe-west1" &&
      !google_bigquery_dataset.revision_validation[0].delete_contents_on_destroy &&
      length(google_bigquery_dataset.revision_validation[0].access) == 1 &&
      alltrue([for entry in google_bigquery_dataset.revision_validation[0].access :
        entry.role == "OWNER" && entry.special_group == "projectOwners"
      ])
    )
    error_message = "Retain the same private dataset without enabling content deletion."
  }
  assert {
    condition = (
      toset(keys(google_bigquery_table.revision_validation)) == toset([
        "analysis_revisions", "revision_result_rows", "revision_attempts", "event_selections"
      ]) &&
      alltrue([for name, table in google_bigquery_table.revision_validation :
        table.dataset_id == "runwx_revision_demo" && table.table_id == name && table.deletion_protection
      ])
    )
    error_message = "Keep the four existing table addresses and deletion protection."
  }
  assert {
    condition = (
      length(google_bigquery_dataset.staging) == 0 &&
      length(google_bigquery_table.synthetic_results) == 0 &&
      length(google_bigquery_dataset.dbt_demo) == 0 &&
      length(google_cloud_run_v2_job.report) == 0 &&
      length(google_cloud_run_v2_job.dbt) == 0 &&
      length(google_service_account.dbt_runtime) == 0
    )
    error_message = "Retaining storage must not enable warehouse demos or Cloud Run jobs."
  }
}
