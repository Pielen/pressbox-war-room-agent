# ⚾🏒 PressBox War Room — Multi-Agent MLB & NHL Scouting & Matchup Analytics Agent

[![Built with Google ADK](https://img.shields.io/badge/Google%20ADK-Python%20v1.0+-4285F4?logo=google)](https://google.github.io/adk-docs/)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python)](https://www.python.org/)
[![OpenTelemetry](https://img.shields.io/badge/Tracing-OpenTelemetry-F5A800?logo=opentelemetry)](https://opentelemetry.io/)
[![Terraform Ready](https://img.shields.io/badge/IaC-Terraform%20%2B%20Cloud%20Run-7B42BC?logo=terraform)](./deployment/terraform/)

## 1. Problem & Solution Statement

### The Problem
Preparing pre-game scouting reports, head-to-head tactical matchup breakdowns, and win-probability projections across **Major League Baseball (MLB)** and the **National Hockey League (NHL)** is fragmented and time-consuming. Broadcasters, sports analysts, front-office scouts, and fantasy managers must manually cross-reference probable starting pitchers/goaltenders, handedness platoon splits (`vs LHP` / `vs RHP` OPS), special teams efficiency (`PP%` + `PK%` Net Special Teams Index), 5v5 expected goals share (`xGF%`), and Pythagorean/Log5 win probabilities across disparate data feeds—where a single misread stat can invalidate a tactical game plan.

### The Solution
**PressBox War Room** is an autonomous, multi-agent sports scouting and analytics system built on the **Google Agent Development Kit (`adk-python`)**. It pairs a root `WarRoomCoordinator` (`LlmAgent`) with concurrent `MLBScoutAgent` and `NHLScoutAgent` specialists (`ParallelAgent`), persistent analyst watchlists and session memory (`ToolContext.state` + `InMemoryMemoryService`), and an iterative **Synthesizer + Statistical Verifier Critic Loop** (`LoopAgent` with `exit_loop`) that audits every cited ERA, WHIP, OPS, PP%, PK%, GSAx, and Log5 win probability before publishing a verified **PressBox Matchup Dossier**.

> **Zero External Sports API Keys Required:** Both the **Official MLB Stats API** (`https://statsapi.mlb.com/api/v1`) and the **Official NHL Web API** (`https://api-web.nhle.com/v1`) are free and unauthenticated, backed by a deterministic local snapshot fallback so CI/CD tests and automated evaluations run 100% reliably offline or online.

---

## 2. Multi-Agent Architecture (`Orchestration & Logic`)

```mermaid
flowchart TD
    User["User / Sports Analyst"] --> Coordinator["WarRoomCoordinator (LlmAgent)\nRoot Router & Memory Orchestrator"]
    
    Coordinator -->|Reads & Persists Watchlists / Notes| Memory["ADK Session State & MemoryService\n(user:watchlist_mlb, user:watchlist_nhl, user:scouting_notes)"]
    Coordinator -->|Direct MLB Lookup| MLBDirect["MLBScoutAgent (LlmAgent)"]
    Coordinator -->|Direct NHL Lookup| NHLDirect["NHLScoutAgent (LlmAgent)"]
    Coordinator -->|Full Dossier Workflow| Pipeline["FullWarRoomPipeline (SequentialAgent)"]
    
    subgraph Step 1: Concurrent Data Collection
        Pipeline --> ParallelGather["ScoutingIntelGatherer (ParallelAgent)"]
        ParallelGather --> ParallelMLB["ParallelMLBScoutAgent (LlmAgent)\noutput_key='mlb_scouting_intel'"]
        ParallelGather --> ParallelNHL["ParallelNHLScoutAgent (LlmAgent)\noutput_key='nhl_scouting_intel'"]
    end
    
    ParallelMLB --> MLBAPI[("Official MLB Stats API\nstatsapi.mlb.com")]
    ParallelNHL --> NHLAPI[("Official NHL Web API\napi-web.nhle.com")]
    
    subgraph Step 2: Iterative Synthesis & Statistical Verification
        Pipeline --> RefineLoop["ReportRefinementLoop (LoopAgent, max_iterations=2)"]
        RefineLoop --> Synthesizer["TacticalSynthesizerAgent (LlmAgent)\nComputes Pythagorean & Log5 Edges\noutput_key='dossier_draft'"]
        Synthesizer --> Critic["StatVerifierCriticAgent (LlmAgent)\nCross-checks stats vs raw tool state\nCalls verify_and_approve_dossier -> exit_loop"]
    end
    
    Critic -->|Verified Dossier| FinalOutput["Broadcast-Ready Scouting & Matchup Dossier"]
```

---

## 3. Alignment with the 5 Automated Evaluation Pillars

| Evaluation Pillar | Implementation Highlights | Key Source Files |
| :--- | :--- | :--- |
| **1. Tool & Interface Design** | **8 strongly-typed, modular tools** covering MLB probable starters & splits, NHL goalies & special teams (`PP%` + `PK%`), Bill James Pythagorean Expectancy ($\gamma=1.83$ MLB, $\gamma=2.05$ NHL) & Log5 head-to-head win probabilities, watchlist persistence, and loop verification. Resilient HTTP timeouts with deterministic fallback cache. | [`mlb_tools.py`](./pressbox_war_room/tools/mlb_tools.py), [`nhl_tools.py`](./pressbox_war_room/tools/nhl_tools.py), [`analytics_tools.py`](./pressbox_war_room/tools/analytics_tools.py), [`memory_tools.py`](./pressbox_war_room/tools/memory_tools.py) |
| **2. Context & Memory** | Structured ADK session state prefixes (`user:watchlist_mlb`, `user:watchlist_nhl`, `user:scouting_notes`, `temp:mlb_intel`, `temp:nhl_intel`, `temp:matchup_edges`), cross-agent `output_key` state injection (`{mlb_scouting_intel}`, `{nhl_scouting_intel}`, `{dossier_draft}`), and `InMemorySessionService` + `InMemoryMemoryService` runner factory. | [`memory_tools.py`](./pressbox_war_room/tools/memory_tools.py), [`agent.py`](./pressbox_war_room/agent.py), [`prompts.py`](./pressbox_war_room/prompts.py) |
| **3. Orchestration & Logic** | Combines all core ADK orchestration primitives: `LlmAgent` (`WarRoomCoordinator`), `ParallelAgent` (`ScoutingIntelGatherer`), `SequentialAgent` (`FullWarRoomPipeline`), and `LoopAgent` (`ReportRefinementLoop`) with `StatVerifierCriticAgent` triggering `exit_loop` (`tool_context.actions.escalate = True`) upon statistical verification. | [`agent.py`](./pressbox_war_room/agent.py), [`dossier_pipeline.py`](./pressbox_war_room/sub_agents/dossier_pipeline.py), [`mlb_scout.py`](./pressbox_war_room/sub_agents/mlb_scout.py), [`nhl_scout.py`](./pressbox_war_room/sub_agents/nhl_scout.py) |
| **4. Observability & Tracing** | OpenTelemetry span instrumentation (`opentelemetry.trace`), full ADK lifecycle callbacks (`before_agent_callback`, `after_agent_callback`, `before_model_callback`, `after_model_callback`, `before_tool_callback`, `after_tool_callback`), safety guardrails against prompt injection/game-fixing, session audit trail (`observability:trace_log`), and an ADK Evaluation suite (`scouting_eval.evalset.json`). | [`callbacks.py`](./pressbox_war_room/observability/callbacks.py), [`scouting_eval.evalset.json`](./tests/eval/scouting_eval.evalset.json) |
| **5. Infrastructure & CI/CD** | Containerized with `Dockerfile` (`adk api_server`), Terraform IaC for Google Cloud Run v2 + Vertex AI + Cloud Trace (`deployment/terraform/`), and automated GitHub Actions CI/CD workflows (`ci.yml` & `deploy.yml`). | [`Dockerfile`](./Dockerfile), [`main.tf`](./deployment/terraform/main.tf), [`ci.yml`](./.github/workflows/ci.yml), [`deploy.yml`](./.github/workflows/deploy.yml) |

---

## 4. Quickstart & Local Development

### Prerequisites
- Python 3.11+
- A Gemini API key (`GOOGLE_API_KEY`) from [Google AI Studio](https://aistudio.google.com/) **or** Google Cloud Vertex AI credentials.

### Installation
```bash
# 1. Clone the repository
git clone https://github.com/pielen/pressbox-war-room-agent.git
cd pressbox-war-room-agent

# 2. Install package with ADK and developer tools
pip install -e ".[dev,gcp]"

# 3. Configure environment variables
cp .env.example .env
# Edit .env and set GOOGLE_API_KEY="your-key"
```

### Running the Agent (ADK Web UI, CLI, or API Server)
```bash
# Launch the interactive Google ADK Web UI (http://localhost:8000)
adk web .

# Or interact with the War Room in your terminal
adk run pressbox_war_room

# Or launch the production FastAPI Server
adk api_server --host 0.0.0.0 --port 8080 .
```

### Example Prompts to Try
1. **MLB Matchup Scouting & Sabermetrics:**
   > *"Give me a complete MLB scouting matchup breakdown for the Los Angeles Dodgers (LAD) at the New York Yankees (NYY), including probable starting pitchers, LHP/RHP platoon splits, bullpen ERA, and the Pythagorean + Log5 win probability edge."*
2. **NHL Special Teams & Goaltending Duel:**
   > *"Compare the NHL special teams (PP% and PK% Net Index) and starting goalies (SV%, GAA, GSAx) for the Toronto Maple Leafs (TOR) at the Boston Bruins (BOS), and compute the home-ice Log5 win probability."*
3. **Cross-Sport Watchlist & Persistent Analyst Memory:**
   > *"Add the Edmonton Oilers (EDM) and Atlanta Braves (ATL) to my scouting watchlists with a note to track Connor McDavid's 5v5 xGF% and Chris Sale's slider usage, then generate a full War Room dossier."*

---

## 5. Testing & ADK Evaluation

```bash
# Run unit tests (MLB tools, NHL tools, Pythagorean/Log5 math, memory, orchestration & telemetry)
make test
# Or directly via pytest / unittest:
PYTHONPATH=. python3 -m unittest discover -s tests/unit -p "test_*.py" -v

# Run the Google ADK Evaluation suite against scouting_eval.evalset.json
make eval
```

---

## 6. Cloud Run & Terraform Deployment

```bash
# Build container image locally
make docker-build

# Provision Google Cloud Run v2 service, IAM roles, and Cloud Trace via Terraform
cd deployment/terraform
terraform init
terraform apply -var="project_id=your-gcp-project-id"
```
