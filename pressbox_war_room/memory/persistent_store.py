"""Persistent SQLite / SQL Database Storage for Sessions, Watchlists, and Scouting Memory.

Replaces volatile in-memory-only state with a durable relational database store
(`PersistentScoutingDatabase` + ADK `DatabaseSessionService` integration).
Supports SQLite (with WAL mode for concurrency) out of the box and PostgreSQL /
Cloud SQL via `WAR_ROOM_DATABASE_URL`.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any, Optional
import uuid


class PersistentScoutingDatabase:
    """Durable SQLite/SQL backing store for sessions, watchlists, notes, and compaction checkpoints."""

    def __init__(self, db_path: str | Path = "./pressbox_war_room_state.db") -> None:
        self.db_path = str(db_path)
        self._lock = threading.RLock()
        self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _initialize_schema(self) -> None:
        with self._lock, closing(self._connect()) as conn, conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    app_name TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    compacted_summary TEXT DEFAULT '',
                    updated_at_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS user_watchlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    sport TEXT NOT NULL,
                    team_or_player TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    UNIQUE(user_id, sport, team_or_player)
                );

                CREATE TABLE IF NOT EXISTS scouting_memories (
                    memory_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    sport TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    note TEXT NOT NULL,
                    entity_tags TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_memories_user_sport
                    ON scouting_memories(user_id, sport);

                CREATE TABLE IF NOT EXISTS compaction_checkpoints (
                    checkpoint_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    compacted_turns_count INTEGER NOT NULL,
                    tokens_before INTEGER NOT NULL,
                    tokens_after INTEGER NOT NULL,
                    summary_text TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );
                """
            )

    def upsert_session_state(
        self,
        session_id: str,
        app_name: str,
        user_id: str,
        state: dict[str, Any],
        compacted_summary: str = "",
    ) -> None:
        """Persists session state dictionary and compacted history summary to SQLite."""
        now = datetime.now(timezone.utc).isoformat()
        serializable_state = {
            k: v
            for k, v in state.items()
            if isinstance(v, (str, int, float, bool, list, dict, type(None)))
        }
        with self._lock, closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO sessions (session_id, app_name, user_id, state_json, compacted_summary, updated_at_utc)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    state_json = excluded.state_json,
                    compacted_summary = CASE
                        WHEN excluded.compacted_summary != '' THEN excluded.compacted_summary
                        ELSE sessions.compacted_summary
                    END,
                    updated_at_utc = excluded.updated_at_utc
                """,
                (
                    session_id,
                    app_name,
                    user_id,
                    json.dumps(serializable_state),
                    compacted_summary,
                    now,
                ),
            )

    def load_session_state(self, session_id: str) -> Optional[dict[str, Any]]:
        """Loads a persisted session state dictionary from disk."""
        with self._lock, closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT state_json, compacted_summary FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            state = json.loads(row["state_json"])
            if row["compacted_summary"]:
                state["memory:compacted_history_summary"] = row["compacted_summary"]
            return state

    def sync_user_watchlist(
        self, user_id: str, mlb_teams: list[str], nhl_teams: list[str]
    ) -> None:
        """Atomically synchronizes a user's MLB and NHL watchlists into `user_watchlists`."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM user_watchlists WHERE user_id = ?", (user_id,))
            for team in mlb_teams:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO user_watchlists (user_id, sport, team_or_player, created_at_utc)
                    VALUES (?, 'MLB', ?, ?)
                    """,
                    (user_id, team.upper(), now),
                )
            for team in nhl_teams:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO user_watchlists (user_id, sport, team_or_player, created_at_utc)
                    VALUES (?, 'NHL', ?, ?)
                    """,
                    (user_id, team.upper(), now),
                )

    def get_user_watchlist(self, user_id: str) -> dict[str, list[str]]:
        """Loads a user's persisted MLB and NHL watchlists from SQLite."""
        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT sport, team_or_player FROM user_watchlists WHERE user_id = ? ORDER BY id ASC",
                (user_id,),
            ).fetchall()
        mlb = [r["team_or_player"] for r in rows if r["sport"] == "MLB"]
        nhl = [r["team_or_player"] for r in rows if r["sport"] == "NHL"]
        return {"MLB": mlb, "NHL": nhl}

    def insert_scouting_memory(
        self,
        user_id: str,
        sport: str,
        subject: str,
        note: str,
        entity_tags: Optional[list[str]] = None,
    ) -> str:
        """Inserts a long-term analyst scouting note with extracted entity tags into SQLite."""
        memory_id = f"mem-{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc).isoformat()
        tags = entity_tags or [w.upper() for w in f"{sport} {subject} {note}".split() if len(w) >= 3][:10]
        with self._lock, closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO scouting_memories
                    (memory_id, user_id, sport, subject, note, entity_tags, created_at_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    user_id,
                    sport.upper(),
                    subject,
                    note,
                    json.dumps(tags),
                    now,
                ),
            )
        return memory_id

    def search_scouting_memories(
        self,
        user_id: str,
        query: Optional[str] = None,
        sport: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Queries persisted scouting notes from the SQLite `scouting_memories` table."""
        sql = "SELECT * FROM scouting_memories WHERE user_id = ?"
        params: list[Any] = [user_id]
        if sport and sport.upper() not in ("ALL", "BOTH"):
            sql += " AND sport = ?"
            params.append(sport.upper())
        if query:
            sql += " AND (LOWER(note) LIKE ? OR LOWER(subject) LIKE ? OR LOWER(entity_tags) LIKE ?)"
            q_like = f"%{query.lower()}%"
            params.extend([q_like, q_like, q_like])
        sql += " ORDER BY created_at_utc DESC LIMIT ?"
        params.append(limit)

        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [
            {
                "memory_id": r["memory_id"],
                "sport": r["sport"],
                "subject": r["subject"],
                "note": r["note"],
                "entity_tags": json.loads(r["entity_tags"]),
                "recorded_at_utc": r["created_at_utc"],
            }
            for r in rows
        ]

    def record_compaction_checkpoint(
        self,
        session_id: str,
        compacted_turns_count: int,
        tokens_before: int,
        tokens_after: int,
        summary_text: str,
    ) -> str:
        """Records a conversation history compaction checkpoint in SQLite."""
        checkpoint_id = f"cmp-{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO compaction_checkpoints
                    (checkpoint_id, session_id, compacted_turns_count, tokens_before, tokens_after, summary_text, created_at_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint_id,
                    session_id,
                    compacted_turns_count,
                    tokens_before,
                    tokens_after,
                    summary_text,
                    now,
                ),
            )
        return checkpoint_id
