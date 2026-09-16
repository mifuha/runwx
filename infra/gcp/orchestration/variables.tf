variable "orchestration_project_id" {
  description = "Already bootstrapped, separately approved project with billing; never the data project."
  type        = string
  validation {
    condition = (
      can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.orchestration_project_id)) &&
      var.orchestration_project_id != "runwx-learning-mifuha"
    )
    error_message = "Use a separate existing GCP project, not runwx-learning-mifuha."
  }
}

variable "composer_image" {
  description = "Exact Airflow 3 build which passed the bundle smoke test; no version aliases."
  type        = string
  validation {
    condition     = can(regex("^composer-3-airflow-3\\.[0-9]+\\.[0-9]+-build\\.[0-9]+$", var.composer_image))
    error_message = "Pin an exact composer-3-airflow-3.x.y-build.n image."
  }
}

variable "pypi_packages" {
  description = "Only exact dependency overrides verified against composer_image; never the local Airflow lock."
  type        = map(string)
  default     = {}
  validation {
    condition = alltrue([for name, version in var.pypi_packages :
      !startswith(replace(lower(name), "_", "-"), "apache-airflow") &&
      can(regex("^==[0-9][0-9A-Za-z.+-]*$", version))
    ])
    error_message = "Use exact package pins; Composer owns Airflow and its providers."
  }
}
