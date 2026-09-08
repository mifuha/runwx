output "input_bucket" {
  value = google_storage_bucket.inputs.name
}

output "report_bucket" {
  value = google_storage_bucket.reports.name
}

output "image_repository" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.runwx.repository_id}/runwx"
}

output "job_name" {
  value = one(google_cloud_run_v2_job.report[*].name)
}

output "runtime_service_account" {
  value = google_service_account.runtime.email
}
