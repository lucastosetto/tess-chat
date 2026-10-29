resource "google_storage_bucket" "attachments" {
  name                        = "${var.project_id}-attachments"
  location                    = upper(var.region)
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true

  depends_on = [google_project_service.this]
}
