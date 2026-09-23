"""NHL Specialist Sub-Agent (`NHLScoutAgent`) for the PressBox War Room."""

from __future__ import annotations

try:
    from google.adk.agents import LlmAgent  # type: ignore[import-untyped]
except ImportError:
    from pressbox_war_room._adk_compat import LlmAgent

from pressbox_war_room.config import settings
from pressbox_war_room.observability.callbacks import (
    after_agent_callback,
    after_model_callback,
    after_tool_callback,
    before_agent_callback,
    before_model_callback,
    before_tool_callback,
)
from pressbox_war_room.prompts import NHL_SCOUT_INSTRUCTION
from pressbox_war_room.tools.nhl_tools import (
    get_nhl_schedule_and_matchup,
    get_nhl_standings_snapshot,
    get_nhl_team_special_teams_and_goalies,
)


def build_nhl_scout_agent(name: str = "NHLScoutAgent") -> LlmAgent:
    """Constructs an instance of the NHL Ice Hockey Scouting Specialist LlmAgent."""
    return LlmAgent(
        name=name,
        model=settings.model_name,
        description=(
            "Specialist NHL ice hockey scouting agent that retrieves starting goalie "
            "metrics (SV%, GAA, GSAx), Power Play %, Penalty Kill %, Net Special Teams "
            "Index, 5v5 expected goals share (xGF%), and NHL standings."
        ),
        instruction=NHL_SCOUT_INSTRUCTION,
        tools=[
            get_nhl_schedule_and_matchup,
            get_nhl_team_special_teams_and_goalies,
            get_nhl_standings_snapshot,
        ],
        output_key="nhl_scouting_intel",
        before_agent_callback=before_agent_callback,
        after_agent_callback=after_agent_callback,
        before_model_callback=before_model_callback,
        after_model_callback=after_model_callback,
        before_tool_callback=before_tool_callback,
        after_tool_callback=after_tool_callback,
    )


nhl_scout_agent = build_nhl_scout_agent()
