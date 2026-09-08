# BigQuery API must already be enabled. This first table holds one synthetic export.
variable "enable_bigquery_staging" {
  type        = bool
  default     = false
  description = "Create the private dataset and empty table for the first staging load."
}

resource "google_bigquery_dataset" "staging" {
  count                      = var.enable_bigquery_staging ? 1 : 0
  dataset_id                 = "runwx_staging"
  location                   = var.region
  description                = "Synthetic race-result staging; not historical evidence."
  delete_contents_on_destroy = false
  access {
    role          = "OWNER"
    special_group = "projectOwners"
  }
  lifecycle { prevent_destroy = true }
}

resource "google_bigquery_table" "synthetic_results" {
  count               = var.enable_bigquery_staging ? 1 : 0
  dataset_id          = google_bigquery_dataset.staging[0].dataset_id
  table_id            = "synthetic_results"
  description         = "One synthetic export, schema version 1. No appends or selected historical revision."
  schema              = file("${path.module}/../../src/runwx/adapters/bigquery/result_rows.schema.json")
  deletion_protection = true
  lifecycle { prevent_destroy = true }
}

output "synthetic_results_table" {
  value = var.enable_bigquery_staging ? "${var.project_id}.runwx_staging.synthetic_results" : null
}
