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

variable "gnr_sample_tables" {
  description = "Explicit fixed GNR sample tables; dbt outputs are scoped separately."
  type        = map(string)
  default     = {}
}

variable "dbt_runtime_service_account_email" {
  type        = string
  default     = null
  nullable    = true
  description = "Dedicated dbt Cloud Run identity created by the parent Terraform root."
  validation {
    condition = (
      var.dbt_runtime_service_account_email == null ? true :
      can(regex("^runwx-dbt@[^.]+\\.iam\\.gserviceaccount\\.com$", var.dbt_runtime_service_account_email))
    )
    error_message = "Use the dedicated runwx-dbt service-account email."
  }
}

variable "dbt_runtime_access" {
  type        = map(string)
  default     = {}
  description = "Snapshot keys granted READER or WRITER for one reviewed dbt stage."
  validation {
    condition     = alltrue([for role in values(var.dbt_runtime_access) : contains(["READER", "WRITER"], role)])
    error_message = "dbt_runtime_access values must be READER or WRITER."
  }
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

resource "google_bigquery_table" "gnr_samples" {
  for_each            = var.gnr_sample_tables
  project             = var.project_id
  dataset_id          = data.google_bigquery_dataset.staging.dataset_id
  table_id            = each.value
  description         = "One fixed Great North Run top-1,000 sample with event-window ERA5 context."
  schema              = file("${path.module}/../../../src/runwx/adapters/bigquery/gnr_sample_rows.schema.json")
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
  dynamic "access" {
    for_each = (
      var.dbt_runtime_service_account_email != null && contains(keys(var.dbt_runtime_access), each.key)
      ? [var.dbt_runtime_access[each.key]] : []
    )
    content {
      role          = access.value
      user_by_email = var.dbt_runtime_service_account_email
    }
  }
  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = length(setsubtract(toset(keys(var.dbt_runtime_access)), toset(keys(var.snapshots)))) == 0
      error_message = "Every dbt_runtime_access key must name a managed snapshot."
    }
    precondition {
      condition = (
        (var.dbt_runtime_service_account_email == null && length(var.dbt_runtime_access) == 0) ||
        (var.dbt_runtime_service_account_email != null && length(var.dbt_runtime_access) > 0)
      )
      error_message = "The dbt runtime email and a non-empty access map must be configured together."
    }
  }
}

resource "google_bigquery_table_iam_member" "dbt_runtime_reader" {
  for_each   = var.dbt_runtime_service_account_email == null ? {} : var.dbt_runtime_access
  project    = google_bigquery_table.results[each.key].project
  dataset_id = google_bigquery_table.results[each.key].dataset_id
  table_id   = google_bigquery_table.results[each.key].table_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${var.dbt_runtime_service_account_email}"
}

output "snapshot_tables" {
  value = { for name, table in google_bigquery_table.results : name => "${table.project}.${table.dataset_id}.${table.table_id}" }
}

output "gnr_sample_tables" {
  value = { for name, table in google_bigquery_table.gnr_samples : name => "${table.project}.${table.dataset_id}.${table.table_id}" }
}

output "analysis_datasets" {
  value = { for name, dataset in google_bigquery_dataset.analysis : name => dataset.dataset_id }
}
