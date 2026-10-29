output "project_id" {
  value = google_project.this.project_id
}

output "tfstate_bucket" {
  value = google_storage_bucket.tfstate.name
}
