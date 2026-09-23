"""Root Agent (`WarRoomCoordinator`) and ADK Runner factory for PressBox War Room.

Exposes `root_agent` as the canonical Google ADK entry point (`adk web`, `adk run`,
`adk api_server`, and `AgentEvaluator`).
"""

from __future__ import annotations

try:
    from google.adk.agents import LlmAgent  # type: ignore[import-untyped]
    from google.adk.memory import InMemoryMemoryService  # type: ignore[import-untyped]
    from google.adk.runners import Runner  # type: ignore[import-untyped]
    from google.adk.sessions import InMemorySessionService  # type: ignore[import-untyped]
except ImportError:
    from pressbox_war_room._adk_compat import (
        InMemoryMemoryService,
        InMemorySessionService,
        LlmAgent,
        Runner,
    )

from pressbox_war_room.config import settings
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
        "scout sub-agents, manages persistent scouting watchlists in session memory, "
        "and orchestrates the parallel-gather + critic-verified dossier pipeline."
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


def create_war_room_runner() -> tuple[Runner, InMemorySessionService, InMemoryMemoryService]:
    """Creates an ADK Runner pre-configured with Session and Memory services."""
    session_service = InMemorySessionService()
    memory_service = InMemoryMemoryService()
    runner = Runner(
        agent=root_agent,
        app_name=settings.app_name,
        session_service=session_service,
        memory_service=memory_service,
    )
    return runner, session_service, memory_service
