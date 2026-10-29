output "service_url" {
  value = var.deploy_service ? google_cloud_run_v2_service.app[0].uri : null
}

output "image_repository" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.app.repository_id}"
}

output "attachments_bucket" {
  value = google_storage_bucket.attachments.name
}

output "runtime_service_account" {
  value = google_service_account.runtime.email
}

output "wif_provider" {
  value = local.wif_enabled ? google_iam_workload_identity_pool_provider.github[0].name : null
}

output "deployer_service_account" {
  value = local.wif_enabled ? google_service_account.deployer[0].email : null
}
