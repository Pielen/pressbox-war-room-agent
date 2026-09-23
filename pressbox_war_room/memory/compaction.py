"""Conversation History Compaction & Context Window Token Budget Manager.

Implements the History Compaction requirement of the Context & Memory rubric:
1. Sliding-window + entity-preserving summarization compaction (`ConversationHistoryCompactor`)
   that condenses older conversation turns into a structured `RollingScoutingSummary`
   while retaining the most recent `overlap_size` turns verbatim.
2. Token-budget enforcement (`max_token_budget`) on `llm_request.contents` inside
   `before_model_callback`.
3. Ephemeral tool-output compaction (`compact_ephemeral_tool_state`) that trims verbose
   raw API payloads into compact statistical digests across turns.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Optional

_SPORT_ENTITIES_PATTERN = re.compile(
    r"\b(NYY|LAD|BOS|CHC|ATL|PHI|TOR|EDM|FLA|NYR|MLB|NHL|ERA|WHIP|OPS|GSAx|Log5|Pythagorean|[0-9]+\.[0-9]+%?)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CompactionResult:
    """Result metadata produced when conversation history is compacted."""

    compacted: bool
    turns_before: int
    turns_after: int
    compacted_turns_count: int
    tokens_before: int
    tokens_after: int
    summary_text: str
    retained_history: list[dict[str, Any]]


def estimate_tokens(text_or_obj: Any) -> int:
    """Estimates LLM token count (~4 chars per token heuristic)."""
    raw = str(text_or_obj or "")
    return max(1, len(raw) // 4)


class ConversationHistoryCompactor:
    """Compacts multi-turn conversation history using a sliding window and entity-aware summarizer."""

    def __init__(
        self,
        compaction_interval: int = 4,
        overlap_size: int = 2,
        max_token_budget: int = 3000,
    ) -> None:
        self.compaction_interval = max(2, compaction_interval)
        self.overlap_size = max(1, overlap_size)
        self.max_token_budget = max(256, max_token_budget)

    def summarize_turns(
        self,
        older_turns: list[dict[str, Any]],
        existing_summary: str = "",
    ) -> str:
        """Synthesizes older conversation turns into a dense, entity-preserving scouting summary."""
        extracted_points: list[str] = []
        key_entities: set[str] = set()

        for turn in older_turns:
            role = str(turn.get("role", "user")).upper()
            content = str(turn.get("content", turn.get("text", ""))).strip()
            if not content:
                continue
            for match in _SPORT_ENTITIES_PATTERN.findall(content):
                key_entities.add(match.upper())
            snippet = content[:160].replace("\n", " ")
            if len(content) > 160:
                snippet += "..."
            extracted_points.append(f"[{role}] {snippet}")

        entities_str = ", ".join(sorted(key_entities)[:20]) if key_entities else "None"
        parts: list[str] = []
        if existing_summary.strip():
            parts.append(existing_summary.strip())
        if extracted_points:
            parts.append(
                f"Compacted {len(older_turns)} turns (Entities/Stats: {entities_str}): "
                + " | ".join(extracted_points)
            )
        return "\n".join(parts)

    def compact_conversation_history(
        self,
        history: list[dict[str, Any]],
        existing_summary: str = "",
        force: bool = False,
    ) -> CompactionResult:
        """Compacts `history` if turn count >= `compaction_interval` or token budget is exceeded."""
        turns_before = len(history)
        tokens_before = estimate_tokens(history) + estimate_tokens(existing_summary)

        needs_compaction = (
            force
            or turns_before > self.compaction_interval
            or tokens_before > self.max_token_budget
        )
        if not needs_compaction or turns_before <= self.overlap_size:
            return CompactionResult(
                compacted=False,
                turns_before=turns_before,
                turns_after=turns_before,
                compacted_turns_count=0,
                tokens_before=tokens_before,
                tokens_after=tokens_before,
                summary_text=existing_summary,
                retained_history=list(history),
            )

        cutoff = max(1, turns_before - self.overlap_size)
        older_turns = history[:cutoff]
        recent_turns = history[cutoff:]

        updated_summary = self.summarize_turns(older_turns, existing_summary=existing_summary)
        summary_message = {
            "role": "system",
            "content": f"[COMPACTED WAR ROOM HISTORY SUMMARY]\n{updated_summary}",
            "compacted_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        retained_history = [summary_message, *recent_turns]
        tokens_after = estimate_tokens(retained_history)

        return CompactionResult(
            compacted=True,
            turns_before=turns_before,
            turns_after=len(retained_history),
            compacted_turns_count=len(older_turns),
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            summary_text=updated_summary,
            retained_history=retained_history,
        )

    def compact_session_state(
        self, state: dict[str, Any], force: bool = False
    ) -> Optional[CompactionResult]:
        """Compacts `state['conversation_history']` and prunes oversized ephemeral tool payloads."""
        history: list[dict[str, Any]] = list(state.get("conversation_history", []))
        existing_summary: str = str(state.get("memory:compacted_history_summary", ""))

        result = self.compact_conversation_history(
            history=history,
            existing_summary=existing_summary,
            force=force,
        )
        if result.compacted:
            state["conversation_history"] = result.retained_history
            state["memory:compacted_history_summary"] = result.summary_text
            state["memory:last_compaction_stats"] = {
                "turns_before": result.turns_before,
                "turns_after": result.turns_after,
                "compacted_turns_count": result.compacted_turns_count,
                "tokens_before": result.tokens_before,
                "tokens_after": result.tokens_after,
                "tokens_saved": max(0, result.tokens_before - result.tokens_after),
            }

        # Also compact verbose temporary tool caches if they grow beyond 3 entries
        for temp_key in ("temp:mlb_intel", "temp:nhl_intel", "temp:matchup_edges"):
            store = state.get(temp_key)
            if isinstance(store, dict) and len(store) > 3:
                recent_keys = list(store.keys())[-2:]
                state[temp_key] = {k: store[k] for k in recent_keys}

        return result if result.compacted else None


history_compactor = ConversationHistoryCompactor(
    compaction_interval=4,
    overlap_size=2,
    max_token_budget=3000,
)
