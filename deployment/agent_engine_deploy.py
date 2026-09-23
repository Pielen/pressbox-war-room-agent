"""Deploys PressBox War Room `root_agent` to Google Cloud Vertex AI Agent Engine."""

from __future__ import annotations

import os
from typing import Any

from pressbox_war_room.agent import root_agent
from pressbox_war_room.config import settings


def deploy_to_vertex_agent_engine(
    project_id: str | None = None,
    location: str | None = None,
    staging_bucket: str | None = None,
) -> Any:
    """Packages and deploys `root_agent` to Vertex AI Agent Engine."""
    import vertexai  # type: ignore[import-untyped]
    from vertexai import agent_engines  # type: ignore[import-untyped]
    from vertexai.preview.reasoning_engines import AdkApp  # type: ignore[import-untyped]

    target_project = project_id or settings.google_cloud_project
    target_location = location or settings.google_cloud_location
    bucket = staging_bucket or os.getenv(
        "WAR_ROOM_STAGING_BUCKET", f"gs://{target_project}-agent-engine-staging"
    )

    vertexai.init(
        project=target_project,
        location=target_location,
        staging_bucket=bucket,
    )

    adk_app = AdkApp(
        agent=root_agent,
        enable_tracing=True,
    )

    remote_agent = agent_engines.create(
        adk_app,
        display_name="pressbox-war-room-multi-agent",
        description="Multi-Agent MLB & NHL Scouting & Matchup War Room on Vertex AI Agent Engine",
        requirements=[
            "google-adk>=1.0.0",
            "google-genai>=1.0.0",
            "google-cloud-aiplatform[adk,agent_engines]>=1.70.0",
            "pydantic>=2.7.0",
            "httpx>=0.27.0",
            "opentelemetry-api>=1.25.0",
            "opentelemetry-sdk>=1.25.0",
            "opentelemetry-exporter-gcp-trace>=1.7.0",
        ],
        extra_packages=["pressbox_war_room"],
    )
    return remote_agent


if __name__ == "__main__":
    deployed = deploy_to_vertex_agent_engine()
    print(f"Deployed PressBox War Room to Vertex AI Agent Engine: {deployed}")
