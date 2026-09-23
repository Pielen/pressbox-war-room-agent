"""Root Agent (`WarRoomCoordinator`), ADK App (`EventsCompactionConfig`), and Persistent Runner Factory.

Exposes `root_agent` and `app` as canonical Google ADK entry points (`adk web`,
`adk run`, `adk api_server`, and `AgentEvaluator`), backed by `DatabaseSessionService`,
`PersistentScoutingDatabase`, `EventsCompactionConfig`, and `AsyncBackgroundMemoryManager`.
"""

from __future__ import annotations

try:
    from google.adk.agents import LlmAgent  # type: ignore[import-untyped]
    from google.adk.memory import InMemoryMemoryService  # type: ignore[import-untyped]
    from google.adk.runners import Runner  # type: ignore[import-untyped]
    from google.adk.sessions import (  # type: ignore[import-untyped]
        DatabaseSessionService,
        InMemorySessionService,
    )
    from pressbox_war_room._adk_compat import App, EventsCompactionConfig
except ImportError:
    from pressbox_war_room._adk_compat import (
        App,
        DatabaseSessionService,
        EventsCompactionConfig,
        InMemoryMemoryService,
        InMemorySessionService,
        LlmAgent,
        Runner,
    )

from pressbox_war_room.config import settings
from pressbox_war_room.memory.background_worker import background_memory_manager
from pressbox_war_room.observability.callbacks import (
    after_agent_callback,
    after_model_callback,
    after_tool_callback,
    before_agent_callback,
    before_model_callback,
    before_tool_callback,
)
from pressbox_war_room.prompts import WAR_ROOM_COORDINATOR_INSTRUCTION
from pressbox_war_room.sub_agents.dossier_pipeline import full_war_room_pipeline
from pressbox_war_room.sub_agents.mlb_scout import mlb_scout_agent
from pressbox_war_room.sub_agents.nhl_scout import nhl_scout_agent
from pressbox_war_room.tools.analytics_tools import calculate_advanced_matchup_edge
from pressbox_war_room.tools.memory_tools import manage_scouting_watchlist
from pressbox_war_room.tools.mlb_tools import (
    get_mlb_schedule_and_probables,
    get_mlb_standings_snapshot,
    get_mlb_team_and_pitcher_splits,
)
from pressbox_war_room.tools.nhl_tools import (
    get_nhl_schedule_and_matchup,
    get_nhl_standings_snapshot,
    get_nhl_team_special_teams_and_goalies,
)

root_agent = LlmAgent(
    name="WarRoomCoordinator",
    model=settings.model_name,
    description=(
        "Root coordinator for the PressBox War Room multi-agent MLB & NHL scouting "
        "and tactical matchup analytics system. Routes queries to specialist MLB/NHL "
        "scout sub-agents, manages persistent SQLite scouting watchlists with async "
        "background tasks and history compaction, and orchestrates the parallel-gather "
        "+ critic-verified dossier pipeline."
    ),
    instruction=WAR_ROOM_COORDINATOR_INSTRUCTION,
    tools=[
        manage_scouting_watchlist,
        get_mlb_schedule_and_probables,
        get_mlb_team_and_pitcher_splits,
        get_mlb_standings_snapshot,
        get_nhl_schedule_and_matchup,
        get_nhl_team_special_teams_and_goalies,
        get_nhl_standings_snapshot,
        calculate_advanced_matchup_edge,
    ],
    sub_agents=[
        mlb_scout_agent,
        nhl_scout_agent,
        full_war_room_pipeline,
    ],
    before_agent_callback=before_agent_callback,
    after_agent_callback=after_agent_callback,
    before_model_callback=before_model_callback,
    after_model_callback=after_model_callback,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
)

events_compaction_config = EventsCompactionConfig(
    compaction_interval=settings.compaction_interval,
    overlap_size=settings.compaction_overlap_size,
)

app = App(
    name=settings.app_name,
    root_agent=root_agent,
    events_compaction_config=events_compaction_config,
)


def create_war_room_runner(
    db_url: str | None = None,
) -> tuple[Runner, DatabaseSessionService | InMemorySessionService, InMemoryMemoryService]:
    """Creates an ADK Runner backed by `DatabaseSessionService` (SQLite/SQL) and `PersistentScoutingDatabase`."""
    resolved_db_url = db_url or settings.database_url
    try:
        session_service: DatabaseSessionService | InMemorySessionService = (
            DatabaseSessionService(db_url=resolved_db_url)
        )
    except Exception:  # noqa: BLE001
        session_service = InMemorySessionService()

    memory_service = InMemoryMemoryService()
    runner = Runner(
        agent=root_agent,
        app_name=settings.app_name,
        session_service=session_service,
        memory_service=memory_service,
    )
    return runner, session_service, memory_service


__all__ = [
    "app",
    "background_memory_manager",
    "create_war_room_runner",
    "events_compaction_config",
    "root_agent",
]
