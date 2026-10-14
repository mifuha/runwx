output "uptime_check_id" {
  value = google_monitoring_uptime_check_config.api.uptime_check_id
}

output "alert_policy_name" {
  value = google_monitoring_alert_policy.availability.name
}

output "dashboard_id" {
  value = google_monitoring_dashboard.api.id
}
