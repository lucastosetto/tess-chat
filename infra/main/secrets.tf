resource "google_secret_manager_secret" "this" {
  for_each  = toset(var.secret_names)
  secret_id = each.value

  replication {
    auto {}
  }

  depends_on = [google_project_service.this]
}
