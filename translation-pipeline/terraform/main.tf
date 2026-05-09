terraform {
  required_version = ">= 1.0"
  
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Enable required APIs
resource "google_project_service" "run" {
  service = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudbuild" {
  service = "cloudbuild.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "storage" {
  service = "storage.googleapis.com"
  disable_on_destroy = false
}

# Create GCS bucket for translations
resource "google_storage_bucket" "translations" {
  name          = var.bucket_name
  location      = var.region
  force_destroy = false
  
  uniform_bucket_level_access = true
  
  versioning {
    enabled = true
  }
  
  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type = "Delete"
    }
  }
}

# Cloud Run service
resource "google_cloud_run_service" "translator" {
  name     = "hermes-wiki-translator"
  location = var.region
  
  template {
    spec {
      containers {
        image = "gcr.io/${var.project_id}/hermes-wiki-translator:latest"
        
        env {
          name  = "CLAUDE_API_KEY"
          value = var.claude_api_key
        }
        
        env {
          name  = "GCS_BUCKET_NAME"
          value = google_storage_bucket.translations.name
        }
        
        env {
          name  = "LOCAL_MODE"
          value = "false"
        }
        
        env {
          name  = "MAX_WORKERS"
          value = var.max_workers
        }
        
        env {
          name  = "TRANSLATION_MODEL"
          value = var.translation_model
        }
        
        env {
          name  = "GITHUB_TOKEN"
          value = var.github_token
        }
        
        resources {
          limits = {
            cpu    = "2000m"
            memory = "2Gi"
          }
        }
      }
      
      timeout_seconds = 3600
    }
    
    metadata {
      annotations = {
        "autoscaling.knative.dev/minScale" = "0"
        "autoscaling.knative.dev/maxScale" = var.max_instances
      }
    }
  }
  
  traffic {
    percent         = 100
    latest_revision = true
  }
  
  depends_on = [
    google_project_service.run,
    google_storage_bucket.translations
  ]
}

# Allow unauthenticated access (optional - remove for private service)
resource "google_cloud_run_service_iam_member" "public" {
  count = var.allow_unauthenticated ? 1 : 0
  
  service  = google_cloud_run_service.translator.name
  location = google_cloud_run_service.translator.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Grant Cloud Run service account access to GCS bucket
resource "google_storage_bucket_iam_member" "translator_storage" {
  bucket = google_storage_bucket.translations.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_cloud_run_service.translator.template[0].spec[0].service_account_name}"
}

# Outputs
output "service_url" {
  description = "URL of the Cloud Run service"
  value       = google_cloud_run_service.translator.status[0].url
}

output "bucket_name" {
  description = "Name of the GCS bucket"
  value       = google_storage_bucket.translations.name
}

output "bucket_url" {
  description = "URL of the GCS bucket"
  value       = "gs://${google_storage_bucket.translations.name}"
}
