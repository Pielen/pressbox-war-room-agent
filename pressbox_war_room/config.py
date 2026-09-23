"""Centralized configuration for the PressBox War Room multi-agent system."""

from __future__ import annotations

from dataclasses import dataclass, field
import os


@dataclass(frozen=True)
class WarRoomConfig:
    """Configuration settings loaded from environment variables with safe defaults."""

    app_name: str = field(
        default_factory=lambda: os.getenv("WAR_ROOM_APP_NAME", "pressbox_war_room")
    )
    model_name: str = field(
        default_factory=lambda: os.getenv("WAR_ROOM_MODEL", "gemini-2.5-flash")
    )
    critic_model_name: str = field(
        default_factory=lambda: os.getenv("WAR_ROOM_CRITIC_MODEL", "gemini-2.5-flash")
    )
    use_vertex_ai: bool = field(
        default_factory=lambda: os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "FALSE").upper()
        in ("TRUE", "1", "YES")
    )
    google_cloud_project: str = field(
        default_factory=lambda: os.getenv("GOOGLE_CLOUD_PROJECT", "pressbox-war-room-dev")
    )
    google_cloud_location: str = field(
        default_factory=lambda: os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    )
    mlb_api_base_url: str = field(
        default_factory=lambda: os.getenv(
            "MLB_API_BASE_URL", "https://statsapi.mlb.com/api/v1"
        )
    )
    nhl_api_base_url: str = field(
        default_factory=lambda: os.getenv(
            "NHL_API_BASE_URL", "https://api-web.nhle.com/v1"
        )
    )
    http_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("WAR_ROOM_HTTP_TIMEOUT", "4.0"))
    )
    prefer_offline_fallback: bool = field(
        default_factory=lambda: os.getenv("WAR_ROOM_OFFLINE_FALLBACK", "FALSE").upper()
        in ("TRUE", "1", "YES")
    )
    enable_cloud_trace: bool = field(
        default_factory=lambda: os.getenv("WAR_ROOM_ENABLE_CLOUD_TRACE", "FALSE").upper()
        in ("TRUE", "1", "YES")
    )
    max_refinement_iterations: int = field(
        default_factory=lambda: int(os.getenv("WAR_ROOM_MAX_REFINEMENTS", "2"))
    )
    sqlite_db_path: str = field(
        default_factory=lambda: os.getenv(
            "WAR_ROOM_SQLITE_DB_PATH", "./pressbox_war_room_state.db"
        )
    )
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "WAR_ROOM_DATABASE_URL", "sqlite:///./pressbox_war_room_state.db"
        )
    )
    compaction_interval: int = field(
        default_factory=lambda: int(os.getenv("WAR_ROOM_COMPACTION_INTERVAL", "4"))
    )
    compaction_overlap_size: int = field(
        default_factory=lambda: int(os.getenv("WAR_ROOM_COMPACTION_OVERLAP", "2"))
    )
    max_context_tokens: int = field(
        default_factory=lambda: int(os.getenv("WAR_ROOM_MAX_CONTEXT_TOKENS", "3000"))
    )


settings = WarRoomConfig()
