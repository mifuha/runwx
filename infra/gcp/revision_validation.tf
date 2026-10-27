# Retain ownership of the parked synthetic experiment's existing dataset/tables.
# This restores no revision-selection application or dbt functionality.
variable "enable_revision_validation" {
  type        = bool
  default     = false
  description = "Retain the parked synthetic dataset and four tables in this root's state; leave false for new setups."
}

resource "google_bigquery_dataset" "revision_validation" {
  count                      = var.enable_revision_validation ? 1 : 0
  dataset_id                 = "runwx_revision_demo"
  location                   = var.region
  description                = "Synthetic revision-selector validation; not historical race evidence."
  delete_contents_on_destroy = false
  access {
    role          = "OWNER"
    special_group = "projectOwners"
  }
  lifecycle { prevent_destroy = true }
}

resource "google_bigquery_table" "revision_validation" {
  for_each = var.enable_revision_validation ? toset([
    "analysis_revisions", "revision_result_rows", "revision_attempts", "event_selections"
  ]) : toset([])

  dataset_id          = google_bigquery_dataset.revision_validation[0].dataset_id
  table_id            = each.value
  description         = "Synthetic revision validation: ${each.value}."
  schema              = file("${path.module}/../../dbt/contracts/revisions/${each.value}.schema.json")
  deletion_protection = true
  lifecycle { prevent_destroy = true }
}
