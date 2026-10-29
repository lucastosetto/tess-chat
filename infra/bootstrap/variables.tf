variable "billing_account" {
  type = string
}

variable "project_prefix" {
  type    = string
  default = "tess-chat"
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "budget_amount" {
  type    = number
  default = 5
}

variable "budget_currency" {
  type    = string
  default = "BRL"
}

variable "org_id" {
  type    = string
  default = null
}
