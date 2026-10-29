locals {
  wif_enabled = var.github_repo != ""
}

resource "google_iam_workload_identity_pool" "github" {
  count                     = local.wif_enabled ? 1 : 0
  workload_identity_pool_id = "github"
  depends_on                = [google_project_service.this]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  count                              = local.wif_enabled ? 1 : 0
  workload_identity_pool_id          = google_iam_workload_identity_pool.github[0].workload_identity_pool_id
  workload_identity_pool_provider_id = "github-actions"
  attribute_condition                = "assertion.repository == \"${var.github_repo}\""

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "deployer" {
  count        = local.wif_enabled ? 1 : 0
  account_id   = "${var.service_name}-deployer"
  display_name = "GitHub Actions deployer"
}

resource "google_service_account_iam_member" "deployer_wif" {
  count              = local.wif_enabled ? 1 : 0
  service_account_id = google_service_account.deployer[0].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github[0].name}/attribute.repository/${var.github_repo}"
}

resource "google_project_iam_member" "deployer" {
  for_each = local.wif_enabled ? toset(["roles/run.developer", "roles/artifactregistry.writer"]) : toset([])
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.deployer[0].email}"
}

resource "google_service_account_iam_member" "deployer_acts_as_runtime" {
  count              = local.wif_enabled ? 1 : 0
  service_account_id = google_service_account.runtime.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer[0].email}"
}
