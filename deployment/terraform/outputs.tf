output "cloud_run_service_uri" {
  description = "Public HTTPS endpoint for the PressBox War Room ADK API server"
  value       = google_cloud_run_v2_service.pressbox_war_room_service.uri
}

output "agent_service_account_email" {
  description = "Service account email used by the ADK agent"
  value       = google_service_account.war_room_agent_sa.email
}
