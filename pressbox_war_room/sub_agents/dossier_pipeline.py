"""Multi-Agent Orchestration Pipeline (`ParallelAgent`, `LoopAgent`, `SequentialAgent`).

Implements the Orchestration & Logic pillar of the evaluation rubric:
1. `ScoutingIntelGatherer` (`ParallelAgent`): Concurrent MLB & NHL data collection.
2. `ReportRefinementLoop` (`LoopAgent`): Iterative synthesis (`TacticalSynthesizerAgent`)
   and statistical verification (`StatVerifierCriticAgent` with `exit_loop`).
3. `FullWarRoomPipeline` (`SequentialAgent`): End-to-end parallel fetch -> loop refinement.
"""

from __future__ import annotations

try:
    from google.adk.agents import (  # type: ignore[import-untyped]
        LlmAgent,
        LoopAgent,
        ParallelAgent,
        SequentialAgent,
    )
except ImportError:
    from pressbox_war_room._adk_compat import (
        LlmAgent,
        LoopAgent,
        ParallelAgent,
        SequentialAgent,
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
from pressbox_war_room.prompts import (
    STAT_VERIFIER_CRITIC_INSTRUCTION,
    TACTICAL_SYNTHESIZER_INSTRUCTION,
)
from pressbox_war_room.sub_agents.mlb_scout import build_mlb_scout_agent
from pressbox_war_room.sub_agents.nhl_scout import build_nhl_scout_agent
from pressbox_war_room.tools.analytics_tools import calculate_advanced_matchup_edge
from pressbox_war_room.tools.memory_tools import verify_and_approve_dossier

# 1. Parallel Scouting Intelligence Gatherer
scouting_intel_gatherer = ParallelAgent(
    name="ScoutingIntelGatherer",
    description=(
        "Executes MLB baseball scouting and NHL ice hockey scouting concurrently "
        "to populate session state (`mlb_scouting_intel` and `nhl_scouting_intel`)."
    ),
    sub_agents=[
        build_mlb_scout_agent(name="ParallelMLBScoutAgent"),
        build_nhl_scout_agent(name="ParallelNHLScoutAgent"),
    ],
    before_agent_callback=before_agent_callback,
    after_agent_callback=after_agent_callback,
)

# 2. Tactical Synthesizer Agent (Drafts Dossier + Quantitative Matchup Edge)
tactical_synthesizer_agent = LlmAgent(
    name="TacticalSynthesizerAgent",
    model=settings.model_name,
    description=(
        "Computes Pythagorean & Log5 win probabilities and synthesizes raw MLB/NHL "
        "scouting intelligence into a structured PressBox Matchup Dossier."
    ),
    instruction=TACTICAL_SYNTHESIZER_INSTRUCTION,
    tools=[calculate_advanced_matchup_edge],
    output_key="dossier_draft",
    before_agent_callback=before_agent_callback,
    after_agent_callback=after_agent_callback,
    before_model_callback=before_model_callback,
    after_model_callback=after_model_callback,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
)

# 3. Statistical Verifier Critic Agent (Audits Numbers & Triggers exit_loop)
stat_verifier_critic_agent = LlmAgent(
    name="StatVerifierCriticAgent",
    model=settings.critic_model_name,
    description=(
        "Audits all statistics cited in `dossier_draft` against raw MLB/NHL tool outputs "
        "and calls `verify_and_approve_dossier` (which invokes `exit_loop` when verified)."
    ),
    instruction=STAT_VERIFIER_CRITIC_INSTRUCTION,
    tools=[verify_and_approve_dossier],
    output_key="critic_review",
    before_agent_callback=before_agent_callback,
    after_agent_callback=after_agent_callback,
    before_model_callback=before_model_callback,
    after_model_callback=after_model_callback,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
)

# 4. Iterative Quality Refinement LoopAgent
report_refinement_loop = LoopAgent(
    name="ReportRefinementLoop",
    description=(
        "Iteratively drafts and fact-checks the PressBox Scouting Dossier until "
        "all cited MLB/NHL metrics are verified or max_iterations is reached."
    ),
    sub_agents=[tactical_synthesizer_agent, stat_verifier_critic_agent],
    max_iterations=settings.max_refinement_iterations,
    before_agent_callback=before_agent_callback,
    after_agent_callback=after_agent_callback,
)

# 5. End-to-End Sequential Dossier Pipeline
full_war_room_pipeline = SequentialAgent(
    name="FullWarRoomPipeline",
    description=(
        "End-to-end War Room workflow that runs `ScoutingIntelGatherer` (ParallelAgent) "
        "followed by `ReportRefinementLoop` (LoopAgent) to deliver a verified scouting report."
    ),
    sub_agents=[scouting_intel_gatherer, report_refinement_loop],
    before_agent_callback=before_agent_callback,
    after_agent_callback=after_agent_callback,
)
