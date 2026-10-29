terraform {
  required_version = ">= 1.9"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
  backend "gcs" {
    bucket = "tess-chat-19db69-tfstate"
    prefix = "main"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
