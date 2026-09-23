"""Root Agent (`WarRoomCoordinator`), ADK App with `EventsCompactionConfig`, and Persistent Runner Factory.

Exposes `root_agent` and `app` as canonical Google ADK entry points (`adk web`, `adk run`,
`adk api_server`, and `AgentEvaluator`), wired with:
- Persistent SQLite / SQL database (`DatabaseSessionService` + `SQLiteScoutingMemoryDatabase`)
- Sliding-window conversation history compaction (`EventsCompactionConfig` + `ConversationHistoryCompactor`)
- Non-blocking background memory execution (`AsyncBackgroundMemoryManager`)
"""

from __future__ import annotations

from typing import Any

try:
    from google.adk.agents import LlmAgent  # type: ignore[import-untyped]
    from google.adk.apps.app import App  # type: ignore[import-untyped]
    from google.adk.memory import InMemoryMemoryService  # type: ignore[import-untyped]
    from google.adk.runners import Runner  # type: ignore[import-untyped]
except ImportError:
    from pressbox_war_room._adk_compat import (
        InMemoryMemoryService,
        LlmAgent,
        Runner,
    )

    class App:  # type: ignore[no-redef]
        """Compatible ADK App wrapper binding root_agent and events_compaction_config."""

        def __init__(
            self,
            name: str,
            root_agent: Any,
            events_compaction_config: Any = None,
        ) -> None:
            self.name = name
            self.root_agent = root_agent
            self.events_compaction_config = events_compaction_config


from pressbox_war_room.config import settings
from pressbox_war_room.memory import (
    DEFAULT_DATABASE_URL,
    DEFAULT_EVENTS_COMPACTION_CONFIG,
    background_memory_manager,
    create_persistent_adk_session_service,
    history_compactor,
    persistent_memory_db,
)
from pressbox_war_room.observability.callbacks import (
    after_agent_callback,
    after_model_callback,
    after_tool_callback,
    before_agent_callback,
    before_model_callback,
    before_tool_callback,
    on_model_error_callback,
    on_tool_error_callback,
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
from pressbox_war_room.hitl import (
    approve_or_reject_high_stakes_action,
    enforce_hitl_verification_gate,
    publish_official_war_room_dossier,
    request_human_approval_for_high_stakes_action,
)

root_agent = LlmAgent(
    name="WarRoomCoordinator",
    model=settings.model_name,
    description=(
        "Root coordinator for the PressBox War Room multi-agent MLB & NHL scouting "
        "and tactical matchup analytics system. Routes queries to specialist MLB/NHL "
        "scout sub-agents, manages persistent scouting watchlists in SQLite & session memory "
        "via non-blocking background tasks, compacts long conversation history, enforces "
        "Human-in-the-Loop (HITL) verification hooks for high-stakes actions, and "
        "orchestrates the parallel-gather + critic-verified dossier pipeline."
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
        request_human_approval_for_high_stakes_action,
        approve_or_reject_high_stakes_action,
        publish_official_war_room_dossier,
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
    on_model_error_callback=on_model_error_callback,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
    on_tool_error_callback=on_tool_error_callback,
)

app = App(
    name=settings.app_name,
    root_agent=root_agent,
    events_compaction_config=DEFAULT_EVENTS_COMPACTION_CONFIG,
)


def create_war_room_runner(
    db_url: str = DEFAULT_DATABASE_URL,
) -> tuple[Runner, Any, InMemoryMemoryService]:
    """Creates an ADK Runner backed by `DatabaseSessionService` (SQLite/PostgreSQL) and MemoryService."""
    session_service = create_persistent_adk_session_service(db_url=db_url)
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
    "history_compactor",
    "persistent_memory_db",
    "root_agent",
]
