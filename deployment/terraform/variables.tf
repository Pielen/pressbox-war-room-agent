variable "project_id" {
  description = "Google Cloud Project ID hosting PressBox War Room"
  type        = string
}

variable "region" {
  description = "Google Cloud region for Cloud Run and Vertex AI"
  type        = string
  default     = "us-central1"
}

variable "service_name" {
  description = "Name of the Cloud Run v2 service"
  type        = string
  default     = "pressbox-war-room-agent"
}

variable "container_image" {
  description = "Artifact Registry container image URI"
  type        = string
  default     = "us-central1-docker.pkg.dev/pressbox-war-room/agent:latest"
}

variable "model_name" {
  description = "Gemini model identifier for ADK agents"
  type        = string
  default     = "gemini-2.5-flash"
}
