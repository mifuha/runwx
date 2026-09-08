# dbt owns the views; Terraform owns only their private dataset.
variable "enable_dbt_demo" {
  type        = bool
  default     = false
  description = "Create the private output dataset for the first synthetic dbt models."
}

resource "google_bigquery_dataset" "dbt_demo" {
  count                      = var.enable_dbt_demo ? 1 : 0
  dataset_id                 = "runwx_dbt_demo"
  location                   = var.region
  description                = "Synthetic dbt demonstration; not historical race evidence."
  delete_contents_on_destroy = false
  access {
    role          = "OWNER"
    special_group = "projectOwners"
  }
  lifecycle { prevent_destroy = true }
}
