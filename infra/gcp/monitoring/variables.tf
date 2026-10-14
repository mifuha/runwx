variable "project_id" {
  description = "Existing project that serves the public comparison."
  type        = string
  default     = "runwx-learning-mifuha"

  validation {
    condition     = var.project_id == "runwx-learning-mifuha"
    error_message = "This monitoring root is limited to the existing runwx project."
  }
}

variable "notification_email" {
  description = "Approved alert recipient. Keep the value in an ignored tfvars file."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.notification_email))
    error_message = "Supply one email address without whitespace."
  }
}
