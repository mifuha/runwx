variable "project_id" {
  description = "Existing runwx data project; this root does not create or enable it."
  type        = string
  validation {
    condition     = var.project_id == "runwx-learning-mifuha"
    error_message = "The current API catalog is fixed to the runwx-learning-mifuha marts."
  }
}

variable "region" {
  description = "Region shared by the service and its BigQuery dependencies."
  type        = string
  default     = "europe-west1"
  validation {
    condition     = var.region == "europe-west1"
    error_message = "The current API catalog and BigQuery client are fixed to europe-west1."
  }
}

variable "image_uri" {
  description = "Immutable digest for the separately built locked API image."
  type        = string
  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.image_uri))
    error_message = "Use a registry image reference ending in @sha256:<64 lowercase hex digits>."
  }
}
