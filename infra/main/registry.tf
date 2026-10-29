resource "google_artifact_registry_repository" "app" {
  repository_id = var.service_name
  format        = "DOCKER"
  location      = var.region

  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 5
    }
  }

  depends_on = [google_project_service.this]
}
