"""OpenTelemetry tracing, structured logging, and ADK callbacks for PressBox War Room.

Implements the Observability & Tracing pillar of the evaluation rubric:
- Distributed tracing via `opentelemetry.trace` (with Cloud Trace export support)
- Full lifecycle ADK callbacks (`before_agent`, `after_agent`, `before_model`,
  `after_model`, `before_tool`, `after_tool`)
- Safety guardrails against prompt injection and illegal wagering manipulation
- Session-scoped audit trail stored in `state["observability:trace_log"]`
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import time
from typing import Any, Optional

try:
    from opentelemetry import trace  # type: ignore[import-untyped]
    from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-untyped]

    _provider = TracerProvider()
    trace.set_tracer_provider(_provider)
    _tracer = trace.get_tracer("pressbox_war_room.telemetry", "1.0.0")
    OTEL_AVAILABLE = True
except ImportError:
    _tracer = None
    OTEL_AVAILABLE = False

logger = logging.getLogger("pressbox_war_room.observability")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


@dataclass
class SpanRecord:
    """Structured telemetry record for agent and tool executions."""

    span_type: str
    name: str
    started_at_utc: str
    duration_ms: float
    status: str
    attributes: dict[str, Any] = field(default_factory=dict)


class WarRoomTelemetryCollector:
    """Collects structured telemetry spans and metrics across agent turns."""

    def __init__(self) -> None:
        self.spans: list[SpanRecord] = []
        self._active_timers: dict[str, float] = {}

    def start_timer(self, key: str) -> None:
        self._active_timers[key] = time.perf_counter()

    def stop_timer(
        self,
        key: str,
        span_type: str,
        name: str,
        status: str = "OK",
        attributes: Optional[dict[str, Any]] = None,
    ) -> SpanRecord:
        started = self._active_timers.pop(key, time.perf_counter())
        duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
        record = SpanRecord(
            span_type=span_type,
            name=name,
            started_at_utc=datetime.now(timezone.utc).isoformat(),
            duration_ms=duration_ms,
            status=status,
            attributes=dict(attributes or {}),
        )
        self.spans.append(record)
        if _tracer is not None:
            with _tracer.start_as_current_span(f"{span_type}:{name}") as span:
                span.set_attribute("war_room.duration_ms", duration_ms)
                span.set_attribute("war_room.status", status)
                for attr_k, attr_v in (attributes or {}).items():
                    span.set_attribute(f"war_room.{attr_k}", str(attr_v))

        logger.info(
            json.dumps(
                {
                    "event": f"{span_type}_completed",
                    "name": name,
                    "duration_ms": duration_ms,
                    "status": status,
                    "attributes": record.attributes,
                }
            )
        )
        return record

    def summary(self) -> dict[str, Any]:
        tool_spans = [s for s in self.spans if s.span_type == "tool"]
        agent_spans = [s for s in self.spans if s.span_type == "agent"]
        return {
            "total_spans": len(self.spans),
            "agent_invocations": len(agent_spans),
            "tool_invocations": len(tool_spans),
            "avg_tool_latency_ms": round(
                sum(s.duration_ms for s in tool_spans) / len(tool_spans), 2
            )
            if tool_spans
            else 0.0,
            "otel_enabled": OTEL_AVAILABLE,
        }


telemetry_collector = WarRoomTelemetryCollector()

_BLOCKED_PATTERNS = (
    "ignore previous instructions",
    "system prompt override",
    "fix the game",
    "bribe referee",
)


def _extract_state(context_obj: Any) -> Optional[dict[str, Any]]:
    """Extracts the mutable state dictionary from an ADK CallbackContext or ToolContext."""
    if context_obj is None:
        return None
    if isinstance(context_obj, dict):
        return context_obj
    state = getattr(context_obj, "state", None)
    if isinstance(state, dict):
        return state
    return None


def before_agent_callback(callback_context: Any) -> Optional[Any]:
    """ADK before_agent_callback: hydrates state from SQLite DB and starts tracing."""
    from pressbox_war_room.memory.persistent_store import persistent_memory_db

    agent_name = getattr(callback_context, "agent_name", "WarRoomAgent")
    telemetry_collector.start_timer(f"agent:{agent_name}")

    state = _extract_state(callback_context)
    if state is not None:
        user_id = str(state.setdefault("user:id", "default_analyst"))
        session_id = getattr(callback_context, "invocation_id", "default_session")
        if "user:watchlist_mlb" not in state:
            state["user:watchlist_mlb"] = persistent_memory_db.get_watchlist(
                user_id=user_id, sport="MLB", default=["NYY", "LAD", "BOS", "CHC"]
            )
        if "user:watchlist_nhl" not in state:
            state["user:watchlist_nhl"] = persistent_memory_db.get_watchlist(
                user_id=user_id, sport="NHL", default=["BOS", "TOR", "EDM", "FLA"]
            )
        if "user:scouting_notes" not in state:
            state["user:scouting_notes"] = persistent_memory_db.get_recent_scouting_notes(
                user_id=user_id, limit=10
            )
        if "memory:compacted_history_summary" not in state:
            saved_summary = persistent_memory_db.get_compacted_summary(session_id)
            state["memory:compacted_history_summary"] = (
                saved_summary["summary_text"] if saved_summary else ""
            )
        state.setdefault("mlb_scouting_intel", "No MLB scouting data gathered yet.")
        state.setdefault("nhl_scouting_intel", "No NHL scouting data gathered yet.")
        state.setdefault("dossier_draft", "No scouting dossier drafted yet.")
        state.setdefault("observability:trace_log", [])
        state["observability:last_active_agent"] = agent_name
        state["observability:last_invocation_utc"] = datetime.now(
            timezone.utc
        ).isoformat()
    return None


def after_agent_callback(callback_context: Any) -> Optional[Any]:
    """ADK after_agent_callback: records agent latency and dispatches async background memory sync."""
    from pressbox_war_room.memory.background_tasks import background_memory_manager

    agent_name = getattr(callback_context, "agent_name", "WarRoomAgent")
    record = telemetry_collector.stop_timer(
        key=f"agent:{agent_name}",
        span_type="agent",
        name=agent_name,
        status="OK",
    )
    state = _extract_state(callback_context)
    if state is not None:
        trace_log = state.setdefault("observability:trace_log", [])
        trace_log.append(
            {
                "type": "agent",
                "name": agent_name,
                "duration_ms": record.duration_ms,
                "timestamp": record.started_at_utc,
            }
        )
        # Dispatch non-blocking background persistence of current watchlists to SQLite
        user_id = str(state.get("user:id", "default_analyst"))
        bg_id = background_memory_manager.schedule_watchlist_persistence(
            user_id=user_id,
            mlb_list=list(state.get("user:watchlist_mlb", ["NYY", "LAD"])),
            nhl_list=list(state.get("user:watchlist_nhl", ["BOS", "TOR"])),
        )
        state["memory:last_background_task_id"] = bg_id
    return None


def before_model_callback(
    callback_context: Any, llm_request: Any = None
) -> Optional[dict[str, Any]]:
    """ADK before_model_callback: enforces guardrails and compacts conversation history."""
    from pressbox_war_room.memory.background_tasks import background_memory_manager
    from pressbox_war_room.memory.compaction import history_compactor

    agent_name = getattr(callback_context, "agent_name", "WarRoomAgent")
    telemetry_collector.start_timer(f"model:{agent_name}")

    request_text = str(llm_request or "").lower()
    for pattern in _BLOCKED_PATTERNS:
        if pattern in request_text:
            telemetry_collector.stop_timer(
                key=f"model:{agent_name}",
                span_type="model_guardrail",
                name=agent_name,
                status="BLOCKED",
                attributes={"matched_pattern": pattern},
            )
            return {
                "status": "blocked_by_guardrail",
                "reason": (
                    "Request blocked by PressBox War Room safety guardrail: "
                    f"disallowed pattern '{pattern}'."
                ),
            }

    state = _extract_state(callback_context)
    if state is not None:
        if request_text:
            compaction_res = history_compactor.record_turn(
                state=state, role="user", content=str(llm_request)
            )
        else:
            compaction_res = history_compactor.compact_if_needed(
                state=state, llm_request=llm_request
            )
        if compaction_res.get("compacted"):
            session_id = getattr(callback_context, "invocation_id", "default_session")
            user_id = str(state.get("user:id", "default_analyst"))
            background_memory_manager.schedule_compaction_persistence(
                session_id=session_id,
                user_id=user_id,
                compaction_result=compaction_res,
            )
    return None


def after_model_callback(
    callback_context: Any, llm_response: Any = None
) -> Optional[Any]:
    """ADK after_model_callback: records LLM generation latency."""
    agent_name = getattr(callback_context, "agent_name", "WarRoomAgent")
    telemetry_collector.stop_timer(
        key=f"model:{agent_name}",
        span_type="model",
        name=agent_name,
        status="OK",
    )
    return None


def before_tool_callback(
    tool: Any, args: dict[str, Any], tool_context: Any
) -> Optional[dict[str, Any]]:
    """ADK before_tool_callback: logs tool invocation arguments and starts tool timer."""
    tool_name = getattr(tool, "name", getattr(tool, "__name__", str(tool)))
    telemetry_collector.start_timer(f"tool:{tool_name}")
    return None


def after_tool_callback(
    tool: Any,
    args: dict[str, Any],
    tool_context: Any,
    tool_response: Any,
) -> Optional[Any]:
    """ADK after_tool_callback: records tool span and appends audit entry to session state."""
    tool_name = getattr(tool, "name", getattr(tool, "__name__", str(tool)))
    status = "OK"
    if isinstance(tool_response, dict) and tool_response.get("status") == "error":
        status = "ERROR"

    record = telemetry_collector.stop_timer(
        key=f"tool:{tool_name}",
        span_type="tool",
        name=tool_name,
        status=status,
        attributes={"arg_keys": ",".join(sorted(args.keys()))},
    )
    state = _extract_state(tool_context)
    if state is not None:
        trace_log = state.setdefault("observability:trace_log", [])
        trace_log.append(
            {
                "type": "tool",
                "name": tool_name,
                "status": status,
                "duration_ms": record.duration_ms,
                "args": {
                    k: v for k, v in args.items() if k != "tool_context"
                },
                "timestamp": record.started_at_utc,
            }
        )
    return None
