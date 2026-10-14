locals {
  api_host = "runwx-api-f6n35ol7sa-ew.a.run.app"
  api_filter = join(" AND ", [
    "resource.type = \"cloud_run_revision\"",
    "resource.labels.project_id = \"${var.project_id}\"",
    "resource.labels.service_name = \"runwx-api\"",
    "resource.labels.location = \"europe-west1\"",
  ])
  error_log_filter = "resource.type=\"cloud_run_revision\" resource.labels.service_name=\"runwx-api\" resource.labels.location=\"europe-west1\" severity>=ERROR"
  error_logs_url   = "https://console.cloud.google.com/logs/query;query=${replace(urlencode(local.error_log_filter), "+", "%20")}?project=${var.project_id}"
}

resource "google_monitoring_notification_channel" "email" {
  project      = var.project_id
  display_name = "runwx availability email"
  type         = "email"
  enabled      = true
  force_delete = false
  labels = {
    email_address = var.notification_email
  }
}

resource "google_monitoring_uptime_check_config" "api" {
  project          = var.project_id
  display_name     = "runwx API health"
  timeout          = "10s"
  period           = "300s"
  checker_type     = "STATIC_IP_CHECKERS"
  selected_regions = ["EUROPE", "USA_OREGON", "USA_IOWA"]

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = local.api_host
    }
  }

  http_check {
    path           = "/health"
    port           = 443
    request_method = "GET"
    use_ssl        = true
    validate_ssl   = true

    accepted_response_status_codes {
      status_value = 200
    }
  }

  content_matchers {
    content = "ok"
    matcher = "MATCHES_JSON_PATH"
    json_path_matcher {
      json_path    = "$.status"
      json_matcher = "EXACT_MATCH"
    }
  }
}

resource "google_monitoring_alert_policy" "availability" {
  project               = var.project_id
  display_name          = "runwx API unavailable from multiple locations"
  combiner              = "OR"
  enabled               = true
  notification_channels = [google_monitoring_notification_channel.email.name]

  conditions {
    display_name = "At least two checker locations fail for ten minutes"
    condition_threshold {
      filter = join(" AND ", [
        "metric.type = \"monitoring.googleapis.com/uptime_check/check_passed\"",
        "resource.type = \"uptime_url\"",
        "metric.labels.check_id = \"${google_monitoring_uptime_check_config.api.uptime_check_id}\"",
      ])
      comparison              = "COMPARISON_GT"
      threshold_value         = 1
      duration                = "600s"
      evaluation_missing_data = "EVALUATION_MISSING_DATA_INACTIVE"

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
        group_by_fields      = ["resource.label.host", "resource.label.project_id"]
      }

      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    notification_prompts = ["OPENED", "CLOSED"]
  }

  documentation {
    mime_type = "text/markdown"
    content   = <<-EOT
      The runwx /health check has failed from at least two locations for ten minutes.
      Check [uptime results](https://console.cloud.google.com/monitoring/uptime?project=${var.project_id})
      and [API error logs](${local.error_logs_url}) before changing the service.

      /health checks the HTTP process, not BigQuery or comparison correctness.
      Missing probe data does not open an incident. A closed incident alone is not proof of recovery;
      check that fresh probes pass. Sampling and metric delivery add to detection time.
    EOT
  }
}
