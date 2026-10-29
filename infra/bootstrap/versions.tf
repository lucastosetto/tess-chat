terraform {
  required_version = ">= 1.9"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "google" {
  region = var.region
}

provider "google" {
  alias                 = "billing"
  region                = var.region
  billing_project       = google_project.this.project_id
  user_project_override = true
}
