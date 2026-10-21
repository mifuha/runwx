mock_provider "google" {
  mock_data "google_bigquery_dataset" {
    defaults = {
      dataset_id = "runwx_staging"
      location   = "europe-west1"
    }
  }
}

variables {
  project_id                        = "runwx-learning-mifuha"
  snapshots                         = {}
  gnr_sample_tables                 = {}
  gnr_analysis_dataset_id           = null
  dbt_runtime_service_account_email = null
  dbt_runtime_access                = {}
  berlin_research_tables            = {}
  berlin_analysis_dataset_id        = null
}

run "berlin_is_opt_in" {
  command = plan
  assert {
    condition     = length(google_bigquery_table.berlin_research) == 0 && length(google_bigquery_dataset.berlin_analysis) == 0
    error_message = "Existing configurations must not create Berlin tables or datasets."
  }
}

run "one_protected_research_table_without_other_resources" {
  command = plan
  variables {
    berlin_research_tables = { berlin_2018 = "berlin_2018_research_bfd49c5c5d9c" }
  }
  assert {
    condition = (
      length(google_bigquery_table.berlin_research) == 1 &&
      google_bigquery_table.berlin_research["berlin_2018"].table_id == "berlin_2018_research_bfd49c5c5d9c" &&
      google_bigquery_table.berlin_research["berlin_2018"].project == var.project_id &&
      google_bigquery_table.berlin_research["berlin_2018"].dataset_id == "runwx_staging" &&
      google_bigquery_table.berlin_research["berlin_2018"].deletion_protection &&
      google_bigquery_table.berlin_research["berlin_2018"].schema == file("${path.module}/../../../src/runwx/adapters/bigquery/berlin_research_rows.schema.json")
    )
    error_message = "Use only the exact protected Berlin snapshot with its own schema."
  }
  assert {
    condition = (
      length(google_bigquery_table.results) == 0 &&
      length(google_bigquery_table.gnr_samples) == 0 &&
      length(google_bigquery_dataset.analysis) == 0 &&
      length(google_bigquery_dataset.gnr_analysis) == 0 &&
      length(google_bigquery_dataset.berlin_analysis) == 0 &&
      length(google_bigquery_table_iam_member.dbt_runtime_reader) == 0
    )
    error_message = "A Berlin table must not imply datasets, existing-source tables or IAM grants."
  }
}

run "one_private_output_dataset_without_tables_or_grants" {
  command = plan
  variables {
    berlin_analysis_dataset_id = "runwx_dbt_berlin_research_v1"
  }
  assert {
    condition = (
      length(google_bigquery_dataset.berlin_analysis) == 1 &&
      google_bigquery_dataset.berlin_analysis[0].project == var.project_id &&
      google_bigquery_dataset.berlin_analysis[0].dataset_id == "runwx_dbt_berlin_research_v1" &&
      google_bigquery_dataset.berlin_analysis[0].location == "europe-west1" &&
      !google_bigquery_dataset.berlin_analysis[0].delete_contents_on_destroy &&
      length(google_bigquery_dataset.berlin_analysis[0].access) == 1 &&
      alltrue([for entry in google_bigquery_dataset.berlin_analysis[0].access : entry.role == "OWNER" && entry.special_group == "projectOwners"]) &&
      output.berlin_analysis_dataset == "runwx_dbt_berlin_research_v1"
    )
    error_message = "Create only the explicit private Berlin dataset in the staging region."
  }
  assert {
    condition = (
      length(google_bigquery_table.berlin_research) == 0 &&
      length(google_bigquery_table.results) == 0 &&
      length(google_bigquery_table.gnr_samples) == 0 &&
      length(google_bigquery_dataset.analysis) == 0 &&
      length(google_bigquery_dataset.gnr_analysis) == 0 &&
      length(google_bigquery_table_iam_member.dbt_runtime_reader) == 0
    )
    error_message = "The output dataset must not imply source tables, other datasets or runtime grants."
  }
}

run "reject_wrong_output_prefix" {
  command = plan
  variables {
    berlin_analysis_dataset_id = "runwx_dbt_gnr_research_v1"
  }
  expect_failures = [var.berlin_analysis_dataset_id]
}

run "reject_output_region_mismatch" {
  command = plan
  variables {
    region                     = "europe-west2"
    berlin_analysis_dataset_id = "runwx_dbt_berlin_research_v1"
  }
  expect_failures = [google_bigquery_dataset.berlin_analysis]
}

run "reject_other_contract" {
  command = plan
  variables {
    berlin_research_tables = { berlin_2018 = "gnr_2018_aaaaaaaaaaaa" }
  }
  expect_failures = [var.berlin_research_tables]
}

run "reject_repeated_destination" {
  command = plan
  variables {
    berlin_research_tables = {
      first  = "berlin_2018_research_bfd49c5c5d9c"
      second = "berlin_2018_research_bfd49c5c5d9c"
    }
  }
  expect_failures = [var.berlin_research_tables]
}

run "reject_wrong_location" {
  command = plan
  variables {
    region                 = "europe-west2"
    berlin_research_tables = { berlin_2018 = "berlin_2018_research_bfd49c5c5d9c" }
  }
  expect_failures = [google_bigquery_table.berlin_research]
}
