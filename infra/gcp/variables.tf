variable "project_id" {
  description = "Existing, approved project with billing attached; Terraform does not create it."
  type        = string
}

variable "region" {
  description = "Keep the job, registry, buckets and later warehouse in one region."
  type        = string
  default     = "europe-west1"
}

variable "image_uri" {
  description = "Null for storage/registry setup; then set the pushed image's immutable digest."
  type        = string
  default     = null
  nullable    = true
  validation {
    condition     = var.image_uri == null ? true : can(regex("@sha256:[0-9a-f]{64}$", var.image_uri))
    error_message = "Use a registry image reference ending in @sha256:<64 lowercase hex digits>."
  }
}

variable "race_object" {
  type    = string
  default = "approved/sample_race_synthetic.html"
}

variable "weather_object" {
  type    = string
  default = "approved/sample_lydd_weather_synthetic.csv"
}

variable "additional_input_objects" {
  description = "Additional immutable input objects approved for execution-time overrides."
  type        = set(string)
  default     = []
  validation {
    condition = alltrue([
      for name in var.additional_input_objects :
      startswith(name, "approved/") && !endswith(name, "/")
    ])
    error_message = "Additional input object names must be files below the approved/ prefix."
  }
}

variable "race_sha256" {
  type    = string
  default = "70095c35dc919ed11506924765def09eb6e5590e3feb95ee7f0e8e9dc6f82182"
}

variable "weather_sha256" {
  type    = string
  default = "835e03b360af5403540aa1f06a99f164ce30140cc958ea9fdbaef301165ca25f"
}

variable "enable_dbt_stage" {
  type        = bool
  default     = false
  description = "Create the manual Cloud Run dbt job and its dedicated runtime identity."
}

variable "dbt_image_uri" {
  description = "Immutable digest for the separately built locked dbt image."
  type        = string
  default     = null
  nullable    = true
  validation {
    condition     = var.dbt_image_uri == null ? true : can(regex("@sha256:[0-9a-f]{64}$", var.dbt_image_uri))
    error_message = "Use a registry image reference ending in @sha256:<64 lowercase hex digits>."
  }
}

variable "dbt_stage_config" {
  description = "Explicit stage-runner configuration; visible in the reviewed Cloud Run job."
  type = object({
    project             = string
    location            = string
    source_dataset      = string
    source_table        = string
    edition_dataset     = string
    comparison_dataset  = string
    comparison_datasets = list(string)
    comparison_baseline = string
    top_n               = number
  })
  default  = null
  nullable = true
  validation {
    condition     = var.dbt_stage_config == null ? true : length(jsonencode(var.dbt_stage_config)) <= 32768
    error_message = "The encoded dbt stage configuration must fit one Cloud Run environment value."
  }
}

variable "dbt_stage_expectations" {
  description = "Frozen analytical expectations; visible in the reviewed Cloud Run job."
  type        = any
  default     = null
  nullable    = true
  validation {
    condition     = var.dbt_stage_expectations == null ? true : length(jsonencode(var.dbt_stage_expectations)) <= 32768
    error_message = "The encoded dbt stage expectations must fit one Cloud Run environment value."
  }
}
