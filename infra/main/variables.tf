variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "service_name" {
  type    = string
  default = "tess-chat"
}

variable "github_repo" {
  type        = string
  default     = ""
  description = "owner/name allowed to deploy via Workload Identity Federation"
}

variable "secret_names" {
  type = list(string)
  default = [
    "gemini-api-key",
    "groq-api-key",
    "anthropic-api-key",
    "tavily-api-key",
    "database-url",
    "google-oauth-client-id",
    "google-oauth-client-secret",
    "session-secret",
  ]
}

variable "deploy_service" {
  type    = bool
  default = false
}

variable "auth_dev_mode" {
  type        = bool
  default     = false
  description = "Enables the email-only dev login; only until Google OAuth is configured"
}

variable "unset_secrets" {
  type        = list(string)
  default     = ["anthropic-api-key", "google-oauth-client-id", "google-oauth-client-secret"]
  description = "Secrets without a version yet; not mapped into Cloud Run"
}
