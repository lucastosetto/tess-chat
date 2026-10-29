resource "google_service_account" "runtime" {
  account_id   = "${var.service_name}-runtime"
  display_name = "Cloud Run runtime"
}

resource "google_storage_bucket_iam_member" "runtime_attachments" {
  bucket = google_storage_bucket.attachments.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_secret_manager_secret_iam_member" "runtime" {
  for_each  = google_secret_manager_secret.this
  secret_id = each.value.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_project_iam_member" "runtime" {
  for_each = toset(["roles/cloudtrace.agent", "roles/logging.logWriter"])
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_service_account_iam_member" "runtime_self_sign" {
  service_account_id = google_service_account.runtime.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.runtime.email}"
}
