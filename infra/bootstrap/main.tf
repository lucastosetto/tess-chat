resource "random_id" "suffix" {
  byte_length = 3
}

resource "google_project" "this" {
  project_id      = "${var.project_prefix}-${random_id.suffix.hex}"
  name            = "Tess Chat"
  org_id          = var.org_id
  billing_account = var.billing_account
  deletion_policy = "DELETE"
}

resource "google_project_service" "bootstrap" {
  for_each = toset([
    "cloudresourcemanager.googleapis.com",
    "serviceusage.googleapis.com",
    "billingbudgets.googleapis.com",
    "storage.googleapis.com",
  ])
  project            = google_project.this.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_storage_bucket" "tfstate" {
  project                     = google_project.this.project_id
  name                        = "${google_project.this.project_id}-tfstate"
  location                    = upper(var.region)
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true

  versioning {
    enabled = true
  }

  depends_on = [google_project_service.bootstrap]
}

resource "google_billing_budget" "this" {
  provider        = google.billing
  billing_account = var.billing_account
  display_name    = "${google_project.this.project_id} budget"

  budget_filter {
    projects = ["projects/${google_project.this.number}"]
  }

  amount {
    specified_amount {
      currency_code = var.budget_currency
      units         = tostring(var.budget_amount)
    }
  }

  dynamic "threshold_rules" {
    for_each = [0.5, 0.9, 1.0]
    content {
      threshold_percent = threshold_rules.value
    }
  }

  depends_on = [google_project_service.bootstrap]
}
