# Separate root/state: the existing infrastructure and parked spike stay owned
# by their original state. This root reads the staging dataset but never owns it.
variable "project_id" {
  type        = string
  description = "Existing approved project; this root does not create or enable services."
}

variable "region" {
  type    = string
  default = "europe-west1"
}

variable "staging_dataset_id" {
  type    = string
  default = "runwx_staging"
}

variable "snapshots" {
  description = "Explicit table and dbt output dataset for each reviewed fixed export."
  type = map(object({
    table_id          = string
    output_dataset_id = string
  }))
  default = {}
}

data "google_bigquery_dataset" "staging" {
  project    = var.project_id
  dataset_id = var.staging_dataset_id
}

resource "google_bigquery_table" "results" {
  for_each            = var.snapshots
  project             = var.project_id
  dataset_id          = data.google_bigquery_dataset.staging.dataset_id
  table_id            = each.value.table_id
  description         = "One fixed historical race/weather export, schema version 1."
  schema              = file("${path.module}/../../../src/runwx/adapters/bigquery/result_rows.schema.json")
  deletion_protection = true

  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = data.google_bigquery_dataset.staging.location == var.region
      error_message = "The existing staging dataset must be in the chosen region."
    }
  }
}

resource "google_bigquery_dataset" "analysis" {
  for_each                   = var.snapshots
  project                    = var.project_id
  dataset_id                 = each.value.output_dataset_id
  location                   = var.region
  description                = "dbt views for one explicitly chosen historical snapshot."
  delete_contents_on_destroy = false
  access {
    role          = "OWNER"
    special_group = "projectOwners"
  }
  lifecycle { prevent_destroy = true }
}

output "snapshot_tables" {
  value = { for name, table in google_bigquery_table.results : name => "${table.project}.${table.dataset_id}.${table.table_id}" }
}

output "analysis_datasets" {
  value = { for name, dataset in google_bigquery_dataset.analysis : name => dataset.dataset_id }
}
