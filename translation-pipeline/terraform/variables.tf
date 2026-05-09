variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP region for resources"
  type        = string
  default     = "us-central1"
}

variable "bucket_name" {
  description = "Name of the GCS bucket for translations"
  type        = string
  default     = "hermes-wiki-translations"
}

variable "claude_api_key" {
  description = "Claude API key from Anthropic"
  type        = string
  sensitive   = true
}

variable "github_token" {
  description = "GitHub personal access token (optional)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "max_workers" {
  description = "Maximum number of parallel translation workers"
  type        = string
  default     = "5"
}

variable "translation_model" {
  description = "Claude model to use for translation"
  type        = string
  default     = "claude-3-5-sonnet-20241022"
}

variable "max_instances" {
  description = "Maximum number of Cloud Run instances"
  type        = string
  default     = "10"
}

variable "allow_unauthenticated" {
  description = "Allow unauthenticated access to the service"
  type        = bool
  default     = true
}
