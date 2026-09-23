"""Context, Session State, and Long-Term Memory Tools for PressBox War Room.

Implements the Context & Memory and Loop Orchestration pillars:
- Persistent user watchlists (`user:watchlist_mlb`, `user:watchlist_nhl`)
- Analyst scouting notebook (`user:scouting_notes`)
- Loop termination and verification state (`verify_and_approve_dossier` / `exit_loop`)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pressbox_war_room._adk_compat import ToolContext, exit_loop


def manage_scouting_watchlist(
    action: str,
    sport: str = "MLB",
    team_or_player: Optional[str] = None,
    scouting_note: Optional[str] = None,
    tool_context: Optional[ToolContext] = None,
) -> dict[str, Any]:
    """Manages the user's persistent MLB & NHL scouting watchlist and analyst notes in ADK session state.

    Args:
        action: One of 'list', 'add', 'remove', or 'add_note'.
        sport: Either 'MLB', 'NHL', or 'BOTH'.
        team_or_player: Team code or player name to add/remove (e.g., 'NYY', 'BOS', 'Shohei Ohtani').
        scouting_note: Optional scouting observation to persist in the user's long-term notebook.
        tool_context: ADK ToolContext providing access to `.state`.

    Returns:
        dict[str, Any]: Updated watchlist and stored analyst notes.
    """
    state = tool_context.state if tool_context is not None else {}
    mlb_list: list[str] = list(state.setdefault("user:watchlist_mlb", ["NYY", "LAD"]))
    nhl_list: list[str] = list(state.setdefault("user:watchlist_nhl", ["BOS", "TOR"]))
    notes: list[dict[str, str]] = list(state.setdefault("user:scouting_notes", []))

    act = action.strip().lower()
    sport_norm = sport.strip().upper()
    target = (team_or_player or "").strip()

    if act == "add" and target:
        if sport_norm in ("MLB", "BASEBALL", "BOTH"):
            if target.upper() not in mlb_list:
                mlb_list.append(target.upper())
        if sport_norm in ("NHL", "HOCKEY", "BOTH"):
            if target.upper() not in nhl_list:
                nhl_list.append(target.upper())

    elif act == "remove" and target:
        if sport_norm in ("MLB", "BASEBALL", "BOTH"):
            mlb_list = [item for item in mlb_list if item.upper() != target.upper()]
        if sport_norm in ("NHL", "HOCKEY", "BOTH"):
            nhl_list = [item for item in nhl_list if item.upper() != target.upper()]

    if scouting_note or (act == "add_note" and target):
        note_text = scouting_note or target
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

    return {
        "status": "success",
        "action": act,
        "watchlist": {
            "MLB": mlb_list,
            "NHL": nhl_list,
        },
        "scouting_notes_count": len(notes),
        "recent_notes": notes[-5:],
    }


def verify_and_approve_dossier(
    verification_passed: bool,
    audited_claims_count: int,
    audit_summary: str,
    corrections_needed: Optional[str] = None,
    tool_context: Optional[ToolContext] = None,
) -> dict[str, Any]:
    """Audits the drafted scouting dossier against raw tool telemetry and exits the refinement loop if verified.

    When `verification_passed=True`, triggers `exit_loop(tool_context)` (`tool_context.actions.escalate = True`)
    to terminate the `ReportRefinementLoop` (`LoopAgent`).

    Args:
        verification_passed: True if all statistics (ERA, OPS, PP%, PK%, Win Prob) match raw tool outputs.
        audited_claims_count: Number of quantitative claims cross-checked against session state.
        audit_summary: Concise explanation of the statistical verification outcome.
        corrections_needed: Specific numerical corrections required if `verification_passed` is False.
        tool_context: ADK ToolContext used to store audit results and trigger loop escalation.

    Returns:
        dict[str, Any]: Verification record and loop escalation status.
    """
    verification_record = {
        "status": "approved" if verification_passed else "revision_required",
        "verification_passed": verification_passed,
        "audited_claims_count": audited_claims_count,
        "audit_summary": audit_summary,
        "corrections_needed": corrections_needed or "None",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    if tool_context is not None:
        tool_context.state["dossier_verification"] = verification_record
        if verification_passed:
            exit_loop(tool_context)

    return verification_record
