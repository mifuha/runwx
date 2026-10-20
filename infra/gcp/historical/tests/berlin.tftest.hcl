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
}

run "berlin_is_opt_in" {
  command = plan
  assert {
    condition     = length(google_bigquery_table.berlin_research) == 0
    error_message = "Existing configurations must not create Berlin tables."
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
      length(google_bigquery_table_iam_member.dbt_runtime_reader) == 0
    )
    error_message = "A Berlin table must not imply datasets, existing-source tables or IAM grants."
  }
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
