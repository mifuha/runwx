output "image_repository" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/runwx/runwx-api"
}

output "service_name" {
  value = google_cloud_run_v2_service.api.name
}

output "service_url" {
  value = google_cloud_run_v2_service.api.uri
}

output "runtime_service_account" {
  value = google_service_account.runtime.email
}
