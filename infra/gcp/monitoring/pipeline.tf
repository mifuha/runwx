variable "enable_dbt_failure_alert" {
  description = "Enable only after the structured dbt failure event is deployed and reviewed."
  type        = bool
  default     = false
}

resource "google_monitoring_alert_policy" "dbt_failure" {
  project               = var.project_id
  display_name          = "runwx dbt execution failed"
  combiner              = "OR"
  enabled               = var.enable_dbt_failure_alert
  notification_channels = [google_monitoring_notification_channel.email.name]

  conditions {
    display_name = "Operational dbt failure event"
    condition_matched_log {
      filter = join(" AND ", [
        "resource.type = \"cloud_run_job\"",
        "resource.labels.project_id = \"${var.project_id}\"",
        "resource.labels.location = \"europe-west1\"",
        "resource.labels.job_name = \"runwx-dbt\"",
        "severity = ERROR",
        "jsonPayload.event = \"runwx_dbt_failure\"",
        "jsonPayload.event_version = 1",
        "jsonPayload.purpose = \"operational\"",
      ])
    }
  }

  alert_strategy {
    notification_rate_limit { period = "900s" }
    auto_close = "86400s"
  }

  documentation {
    mime_type = "text/markdown"
    content   = <<-EOT
      The dbt job reported a failure. Find its execution, edition, stage and error type in
      [job logs](https://console.cloud.google.com/logs/query;query=resource.type%3D%22cloud_run_job%22%20resource.labels.job_name%3D%22runwx-dbt%22?project=${var.project_id}).
      Check retained execution evidence using the instructions in the
      [failure guide](https://github.com/mifuha/runwx/blob/master/docs/pipeline-alerts.md).

      Do not retry blindly: earlier BigQuery views may already exist. A closed incident
      is not proof of recovery. This policy groups failures and limits notifications;
      inspect every execution in the incident window. Cloud Run and Airflow retries
      must remain zero for this job-level failure signal to represent a final attempt.
    EOT
  }
}
