variable "berlin_research_tables" {
  description = "Explicit Berlin research snapshot tables; empty by default."
  type        = map(string)
  default     = {}
  validation {
    condition = (
      length(distinct(values(var.berlin_research_tables))) == length(var.berlin_research_tables) &&
      alltrue([
        for table in values(var.berlin_research_tables) :
        can(regex("^berlin_(200[3-9]|201[0-8])_research_[0-9a-f]{12}$", table))
      ])
    )
    error_message = "Use distinct hash-derived Berlin 2003–2018 research table names."
  }
}

resource "google_bigquery_table" "berlin_research" {
  for_each            = var.berlin_research_tables
  project             = var.project_id
  dataset_id          = data.google_bigquery_dataset.staging.dataset_id
  table_id            = each.value
  description         = "One Berlin research capture with fixed-window ERA5 context; not verified official full-field coverage."
  schema              = file("${path.module}/../../../src/runwx/adapters/bigquery/berlin_research_rows.schema.json")
  deletion_protection = true

  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = data.google_bigquery_dataset.staging.location == var.region
      error_message = "The existing staging dataset must be in the chosen region."
    }
  }
}

output "berlin_research_tables" {
  value = { for name, table in google_bigquery_table.berlin_research : name => "${table.project}.${table.dataset_id}.${table.table_id}" }
}
