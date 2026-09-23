"""Context, Persistent SQLite Database, History Compaction, and Async Memory Tools.

Addresses all 4 pillars of Context & Memory:
1. Clear persona & constraint instructions (`prompts.py`)
2. Conversation history compaction (`history_compactor` / `EventsCompactionConfig`)
3. Persistent relational SQLite database (`persistent_memory_db` + `DatabaseSessionService`)
4. Non-blocking background task execution (`background_memory_manager`)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pressbox_war_room._adk_compat import ToolContext, ValidationError, exit_loop
from pressbox_war_room.memory.background_tasks import background_memory_manager
from pressbox_war_room.memory.compaction import history_compactor
from pressbox_war_room.memory.persistent_store import persistent_memory_db
from pressbox_war_room.tools.schemas import (
    DossierVerificationInput,
    DossierVerificationOutput,
    SUPPORTED_MLB_TEAMS,
    SUPPORTED_NHL_TEAMS,
    ToolInputValidationError,
    WatchlistActionInput,
    WatchlistActionOutput,
    build_validation_error_response,
    with_strict_tool_schema,
)


@with_strict_tool_schema(
    input_model=WatchlistActionInput, output_model=WatchlistActionOutput
)
def manage_scouting_watchlist(
    action: str,
    sport: str = "MLB",
    team_or_player: Optional[str] = None,
    scouting_note: Optional[str] = None,
    tool_context: Optional[ToolContext] = None,
) -> dict[str, Any]:
    """Manages the user's persistent MLB & NHL scouting watchlist and analyst notes.

    Hydrates state from the SQLite database (`persistent_memory_db`) when needed and
    dispatches all write/update operations asynchronously via `background_memory_manager`
    (`asyncio.create_task` / `ThreadPoolExecutor`) so tool execution never blocks on disk I/O.

    Args:
        action: One of 'list', 'add', 'remove', or 'add_note'.
        sport: Either 'MLB', 'NHL', or 'BOTH'.
        team_or_player: Team code ('NYY', 'LAD', 'BOS', 'CHC', 'ATL', 'PHI', 'TOR', 'EDM', 'FLA', 'NYR') or player name.
        scouting_note: Optional scouting observation to persist in the user's long-term notebook.
        tool_context: ADK ToolContext providing access to `.state`.

    Returns:
        dict[str, Any]: Validated `WatchlistActionOutput` dict or `ToolErrorResponse` dict.
    """
    try:
        validated_in = WatchlistActionInput.model_validate(
            {
                "action": action,
                "sport": sport,
                "team_or_player": team_or_player,
                "scouting_note": scouting_note,
            }
        )
    except (ToolInputValidationError, ValidationError) as exc:
        return build_validation_error_response(
            tool_name="manage_scouting_watchlist",
            exc=exc,
            raw_inputs={
                "action": action,
                "sport": sport,
                "team_or_player": team_or_player,
                "scouting_note": scouting_note,
            },
            default_valid_options=list(SUPPORTED_MLB_TEAMS.keys())
            + list(SUPPORTED_NHL_TEAMS.keys()),
        )

    state = tool_context.state if tool_context is not None else {}
    user_id = str(state.get("user:id", "default_analyst"))

    if "user:watchlist_mlb" not in state:
        state["user:watchlist_mlb"] = persistent_memory_db.get_watchlist(
            user_id=user_id, sport="MLB", default=["NYY", "LAD"]
        )
    if "user:watchlist_nhl" not in state:
        state["user:watchlist_nhl"] = persistent_memory_db.get_watchlist(
            user_id=user_id, sport="NHL", default=["BOS", "TOR"]
        )
    if "user:scouting_notes" not in state:
        state["user:scouting_notes"] = persistent_memory_db.get_recent_scouting_notes(
            user_id=user_id, limit=10
        )

    mlb_list: list[str] = list(state["user:watchlist_mlb"])
    nhl_list: list[str] = list(state["user:watchlist_nhl"])
    notes: list[dict[str, str]] = list(state["user:scouting_notes"])

    act = validated_in.action
    sport_norm = validated_in.sport
    target = (validated_in.team_or_player or "").strip()

    if act == "add" and target:
        if sport_norm in ("MLB", "BOTH"):
            if target.upper() not in mlb_list:
                mlb_list.append(target.upper())
        if sport_norm in ("NHL", "BOTH"):
            if target.upper() not in nhl_list:
                nhl_list.append(target.upper())

    elif act == "remove" and target:
        if sport_norm in ("MLB", "BOTH"):
            mlb_list = [item for item in mlb_list if item.upper() != target.upper()]
        if sport_norm in ("NHL", "BOTH"):
            nhl_list = [item for item in nhl_list if item.upper() != target.upper()]

    new_note_entry: Optional[dict[str, str]] = None
    if validated_in.scouting_note or (act == "add_note" and target):
        note_text = validated_in.scouting_note or target
        new_note_entry = {
            "sport": sport_norm,
            "subject": target or "General",
            "note": note_text,
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        notes.append(new_note_entry)

    state["user:watchlist_mlb"] = mlb_list
    state["user:watchlist_nhl"] = nhl_list
    state["user:scouting_notes"] = notes

    # Dispatch persistent SQLite write asynchronously in a background task
    bg_task_id = background_memory_manager.schedule_watchlist_persistence(
        user_id=user_id,
        mlb_list=mlb_list,
        nhl_list=nhl_list,
        new_note=new_note_entry,
    )

    # Also record the memory turn for sliding-window compaction tracking
    compaction_res = history_compactor.record_turn(
        state=state,
        role="tool:manage_scouting_watchlist",
        content=f"action={act} sport={sport_norm} target={target}",
    )
    if compaction_res.get("compacted"):
        session_id = getattr(tool_context, "invocation_id", "default_session")
        background_memory_manager.schedule_compaction_persistence(
            session_id=session_id,
            user_id=user_id,
            compaction_result=compaction_res,
        )

    validated_out = WatchlistActionOutput.model_validate(
        {
            "status": "success",
            "action": act,
            "watchlist": {
                "MLB": mlb_list,
                "NHL": nhl_list,
            },
            "scouting_notes_count": len(notes),
            "recent_notes": notes[-5:],
            "persistence_backend": "sqlite_wal_async",
            "background_task_id": bg_task_id,
        }
    )
    return validated_out.model_dump()


@with_strict_tool_schema(
    input_model=DossierVerificationInput, output_model=DossierVerificationOutput
)
def verify_and_approve_dossier(
    verification_passed: bool,
    audited_claims_count: int,
    audit_summary: str,
    corrections_needed: Optional[str] = None,
    tool_context: Optional[ToolContext] = None,
) -> dict[str, Any]:
    """Audits the drafted scouting dossier against raw tool telemetry and exits the refinement loop if verified.

    Persists verification audits to SQLite asynchronously in a background task (`background_memory_manager`)
    and triggers `exit_loop(tool_context)` when `verification_passed=True`.

    Args:
        verification_passed: True if all statistics (ERA, OPS, PP%, PK%, Win Prob) match raw tool outputs.
        audited_claims_count: Number of quantitative claims cross-checked against session state (>= 1).
        audit_summary: Concise explanation of the statistical verification outcome.
        corrections_needed: Specific numerical corrections required if `verification_passed` is False.
        tool_context: ADK ToolContext used to store audit results and trigger loop escalation.

    Returns:
        dict[str, Any]: Validated `DossierVerificationOutput` dict or `ToolErrorResponse` dict.
    """
    try:
        validated_in = DossierVerificationInput.model_validate(
            {
                "verification_passed": verification_passed,
                "audited_claims_count": audited_claims_count,
                "audit_summary": audit_summary,
                "corrections_needed": corrections_needed,
            }
        )
    except (ToolInputValidationError, ValidationError) as exc:
        return build_validation_error_response(
            tool_name="verify_and_approve_dossier",
            exc=exc,
            raw_inputs={
                "verification_passed": verification_passed,
                "audited_claims_count": audited_claims_count,
                "audit_summary": audit_summary,
                "corrections_needed": corrections_needed,
            },
            default_valid_options=[
                "audited_claims_count >= 1, non-empty corrections_needed when verification_passed=False"
            ],
        )

    session_id = getattr(tool_context, "invocation_id", "default_session")
    now_utc = datetime.now(timezone.utc).isoformat()
    raw_record = {
        "status": "approved" if validated_in.verification_passed else "revision_required",
        "verification_passed": validated_in.verification_passed,
        "audited_claims_count": validated_in.audited_claims_count,
        "audit_summary": validated_in.audit_summary,
        "corrections_needed": validated_in.corrections_needed or "None",
        "verified_at_utc": now_utc,
    }

    bg_task_id = background_memory_manager.schedule_dossier_audit_persistence(
        session_id=session_id,
        verification_record=raw_record,
    )
    raw_record["background_task_id"] = bg_task_id

    validated_out = DossierVerificationOutput.model_validate(raw_record)
    verification_record = validated_out.model_dump()

    if tool_context is not None:
        tool_context.state["dossier_verification"] = verification_record
        if validated_in.verification_passed:
            exit_loop(tool_context)

    return verification_record
