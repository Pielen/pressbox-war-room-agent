"""MLB Specialist Sub-Agent (`MLBScoutAgent`) for the PressBox War Room."""

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
from pressbox_war_room.prompts import MLB_SCOUT_INSTRUCTION
from pressbox_war_room.tools.mlb_tools import (
    get_mlb_schedule_and_probables,
    get_mlb_standings_snapshot,
    get_mlb_team_and_pitcher_splits,
)


def build_mlb_scout_agent(name: str = "MLBScoutAgent") -> LlmAgent:
    """Constructs an instance of the MLB Scouting Specialist LlmAgent."""
    return LlmAgent(
        name=name,
        model=settings.model_name,
        description=(
            "Specialist MLB baseball scouting agent that retrieves probable starting "
            "pitchers, LHP/RHP offensive platoon splits, bullpen ERA, and MLB standings."
        ),
        instruction=MLB_SCOUT_INSTRUCTION,
        tools=[
            get_mlb_schedule_and_probables,
            get_mlb_team_and_pitcher_splits,
            get_mlb_standings_snapshot,
        ],
        output_key="mlb_scouting_intel",
        before_agent_callback=before_agent_callback,
        after_agent_callback=after_agent_callback,
        before_model_callback=before_model_callback,
        after_model_callback=after_model_callback,
        before_tool_callback=before_tool_callback,
        after_tool_callback=after_tool_callback,
    )


mlb_scout_agent = build_mlb_scout_agent()
