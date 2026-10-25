mock_provider "google" {}

variables {
  notification_email = "alerts@example.com"
}

run "health_probe_is_small_and_does_not_query_the_warehouse" {
  command = plan

  assert {
    condition = (
      google_monitoring_uptime_check_config.api.period == "300s" &&
      google_monitoring_uptime_check_config.api.timeout == "10s" &&
      toset(google_monitoring_uptime_check_config.api.selected_regions) == toset(["EUROPE", "USA_OREGON", "USA_IOWA"]) &&
      google_monitoring_uptime_check_config.api.monitored_resource[0].labels.host == "runwx-api-f6n35ol7sa-ew.a.run.app" &&
      google_monitoring_uptime_check_config.api.http_check[0].path == "/health" &&
      google_monitoring_uptime_check_config.api.http_check[0].request_method == "GET"
    )
    error_message = "Use the existing process-only health endpoint every five minutes from exactly three checker locations."
  }

  assert {
    condition = (
      google_monitoring_uptime_check_config.api.http_check[0].use_ssl &&
      google_monitoring_uptime_check_config.api.http_check[0].validate_ssl &&
      google_monitoring_uptime_check_config.api.http_check[0].port == 443 &&
      google_monitoring_uptime_check_config.api.http_check[0].accepted_response_status_codes[0].status_value == 200 &&
      google_monitoring_uptime_check_config.api.content_matchers[0].matcher == "MATCHES_JSON_PATH" &&
      try(jsondecode(google_monitoring_uptime_check_config.api.content_matchers[0].content), null) == "ok" &&
      google_monitoring_uptime_check_config.api.content_matchers[0].json_path_matcher[0].json_path == "$.status"
    )
    error_message = "A passing probe needs a valid TLS certificate, HTTP 200 and the expected JSON health status."
  }
}

run "alert_ignores_one_failed_location_and_waits_for_repeated_failures" {
  command = plan

  override_resource {
    target          = google_monitoring_uptime_check_config.api
    override_during = plan
    values          = { uptime_check_id = "test-health-check" }
  }

  override_resource {
    target          = google_monitoring_notification_channel.email
    override_during = plan
    values          = { name = "projects/runwx-learning-mifuha/notificationChannels/test-channel" }
  }

  assert {
    condition = (
      google_monitoring_alert_policy.availability.conditions[0].condition_threshold[0].comparison == "COMPARISON_GT" &&
      google_monitoring_alert_policy.availability.conditions[0].condition_threshold[0].threshold_value == 1 &&
      google_monitoring_alert_policy.availability.conditions[0].condition_threshold[0].duration == "600s" &&
      google_monitoring_alert_policy.availability.conditions[0].condition_threshold[0].evaluation_missing_data == "EVALUATION_MISSING_DATA_INACTIVE" &&
      google_monitoring_alert_policy.availability.conditions[0].condition_threshold[0].aggregations[0].per_series_aligner == "ALIGN_NEXT_OLDER" &&
      google_monitoring_alert_policy.availability.conditions[0].condition_threshold[0].aggregations[0].cross_series_reducer == "REDUCE_COUNT_FALSE" &&
      google_monitoring_alert_policy.availability.conditions[0].condition_threshold[0].aggregations[0].alignment_period == "300s"
    )
    error_message = "Count failed locations, tolerate one, wait ten minutes and do not treat absent probe data as a service failure."
  }

  assert {
    condition = (
      strcontains(google_monitoring_alert_policy.availability.conditions[0].condition_threshold[0].filter, "metric.labels.check_id = \"test-health-check\"") &&
      google_monitoring_alert_policy.availability.notification_channels == tolist(["projects/runwx-learning-mifuha/notificationChannels/test-channel"]) &&
      toset(google_monitoring_alert_policy.availability.alert_strategy[0].notification_prompts) == toset(["OPENED", "CLOSED"])
    )
    error_message = "The policy must watch this check only and send opening/closing notifications to its approved channel."
  }
}

run "dashboard_uses_only_native_api_metrics" {
  command = plan

  assert {
    condition = alltrue([
      for widget in slice(jsondecode(google_monitoring_dashboard.api.dashboard_json).gridLayout.widgets, 0, 3) :
      strcontains(widget.xyChart.dataSets[0].timeSeriesQuery.timeSeriesFilter.filter, "resource.labels.service_name = \"runwx-api\"") &&
      strcontains(widget.xyChart.dataSets[0].timeSeriesQuery.timeSeriesFilter.filter, "resource.labels.project_id = \"runwx-learning-mifuha\"") &&
      strcontains(widget.xyChart.dataSets[0].timeSeriesQuery.timeSeriesFilter.filter, "metric.type = \"run.googleapis.com/")
    ])
    error_message = "Dashboard queries must stay on native metrics for the existing API."
  }
}

run "reject_wrong_project" {
  command = plan
  variables {
    project_id = "another-project"
  }
  expect_failures = [var.project_id]
}

run "reject_missing_email" {
  command = plan
  variables {
    notification_email = ""
  }
  expect_failures = [var.notification_email]
}

run "dbt_alert_is_disabled_and_scoped" {
  command = plan
  assert {
    condition = (
      !google_monitoring_alert_policy.dbt_failure.enabled &&
      strcontains(google_monitoring_alert_policy.dbt_failure.conditions[0].condition_matched_log[0].filter, "resource.type = \"cloud_run_job\"") &&
      strcontains(google_monitoring_alert_policy.dbt_failure.conditions[0].condition_matched_log[0].filter, "resource.labels.job_name = \"runwx-dbt\"") &&
      strcontains(google_monitoring_alert_policy.dbt_failure.conditions[0].condition_matched_log[0].filter, "jsonPayload.purpose = \"operational\"") &&
      strcontains(google_monitoring_alert_policy.dbt_failure.conditions[0].condition_matched_log[0].filter, "jsonPayload.event = \"runwx_dbt_failure\"") &&
      length(coalesce(google_monitoring_alert_policy.dbt_failure.conditions[0].condition_matched_log[0].label_extractors, {})) == 0 &&
      google_monitoring_alert_policy.dbt_failure.alert_strategy[0].notification_rate_limit[0].period == "900s" &&
      google_monitoring_alert_policy.dbt_failure.alert_strategy[0].auto_close == "86400s"
    )
    error_message = "Keep the dbt alert disabled, job/event scoped and rate limited without per-execution alert labels."
  }
}
