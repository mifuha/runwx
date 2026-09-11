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
