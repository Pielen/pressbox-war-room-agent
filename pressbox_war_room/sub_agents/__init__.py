"""Sub-agents package for PressBox War Room."""

from pressbox_war_room.sub_agents.dossier_pipeline import (
    full_war_room_pipeline,
    report_refinement_loop,
    scouting_intel_gatherer,
    stat_verifier_critic_agent,
    tactical_synthesizer_agent,
)
from pressbox_war_room.sub_agents.mlb_scout import build_mlb_scout_agent, mlb_scout_agent
from pressbox_war_room.sub_agents.nhl_scout import build_nhl_scout_agent, nhl_scout_agent

__all__ = [
    "build_mlb_scout_agent",
    "build_nhl_scout_agent",
    "full_war_room_pipeline",
    "mlb_scout_agent",
    "nhl_scout_agent",
    "report_refinement_loop",
    "scouting_intel_gatherer",
    "stat_verifier_critic_agent",
    "tactical_synthesizer_agent",
]
