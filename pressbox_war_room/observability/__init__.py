"""Observability, OpenTelemetry tracing, Pre-Execution Intent Logging, PII Redaction, and Error Recovery."""

from pressbox_war_room.observability.callbacks import (
    WarRoomTelemetryCollector,
    after_agent_callback,
    after_model_callback,
    after_tool_callback,
    before_agent_callback,
    before_model_callback,
    before_tool_callback,
    classify_scouting_intent,
    describe_tool_intent,
    on_model_error_callback,
    on_tool_error_callback,
    telemetry_collector,
)
from pressbox_war_room.observability.pii_redactor import (
    PIIRedactingLogFilter,
    PIIRedactor,
    pii_redactor,
)

__all__ = [
    "PIIRedactingLogFilter",
    "PIIRedactor",
    "WarRoomTelemetryCollector",
    "after_agent_callback",
    "after_model_callback",
    "after_tool_callback",
    "before_agent_callback",
    "before_model_callback",
    "before_tool_callback",
    "classify_scouting_intent",
    "describe_tool_intent",
    "on_model_error_callback",
    "on_tool_error_callback",
    "pii_redactor",
    "telemetry_collector",
]
