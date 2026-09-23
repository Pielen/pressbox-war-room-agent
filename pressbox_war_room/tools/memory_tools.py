"""Context, Session State, and Long-Term Memory Tools for PressBox War Room.

Implements strict Pydantic v2 input/output schema validation (`WatchlistActionInput`,
`WatchlistActionOutput`, `DossierVerificationInput`, `DossierVerificationOutput`)
and guided LLM error recovery (`ToolErrorResponse`).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pressbox_war_room._adk_compat import ToolContext, ValidationError, exit_loop
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
    """Manages the user's persistent MLB & NHL scouting watchlist and analyst notes in ADK session state.

    Validates inputs against `WatchlistActionInput` (Pydantic BaseModel) and output
    against `WatchlistActionOutput`. Returns `ToolErrorResponse` with recovery
    instructions if an invalid action, sport, or team code is provided.

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
    mlb_list: list[str] = list(state.setdefault("user:watchlist_mlb", ["NYY", "LAD"]))
    nhl_list: list[str] = list(state.setdefault("user:watchlist_nhl", ["BOS", "TOR"]))
    notes: list[dict[str, str]] = list(state.setdefault("user:scouting_notes", []))

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

    if validated_in.scouting_note or (act == "add_note" and target):
        note_text = validated_in.scouting_note or target
        notes.append(
            {
                "sport": sport_norm,
                "subject": target or "General",
                "note": note_text,
                "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            }
        )

    state["user:watchlist_mlb"] = mlb_list
    state["user:watchlist_nhl"] = nhl_list
    state["user:scouting_notes"] = notes

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

    Validates inputs against `DossierVerificationInput` (Pydantic BaseModel) and output
    against `DossierVerificationOutput`. Requires `corrections_needed` when
    `verification_passed=False`. When `verification_passed=True`, invokes `exit_loop(tool_context)`.

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
            default_valid_options=["audited_claims_count >= 1, non-empty corrections_needed when verification_passed=False"],
        )

    validated_out = DossierVerificationOutput.model_validate(
        {
            "status": "approved" if validated_in.verification_passed else "revision_required",
            "verification_passed": validated_in.verification_passed,
            "audited_claims_count": validated_in.audited_claims_count,
            "audit_summary": validated_in.audit_summary,
            "corrections_needed": validated_in.corrections_needed or "None",
            "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
    verification_record = validated_out.model_dump()

    if tool_context is not None:
        tool_context.state["dossier_verification"] = verification_record
        if validated_in.verification_passed:
            exit_loop(tool_context)

    return verification_record
