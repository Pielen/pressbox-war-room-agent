"""Memory & Context Management Package for PressBox War Room.

Provides:
- `SQLiteScoutingMemoryDatabase` & `create_persistent_adk_session_service` (Persistent DB)
- `ConversationHistoryCompactor` & `EventsCompactionConfig` (History Compaction)
- `AsyncBackgroundMemoryManager` (Asynchronous Background Memory Operations)
"""

from pressbox_war_room.memory.background_tasks import (
    AsyncBackgroundMemoryManager,
    background_memory_manager,
)
from pressbox_war_room.memory.compaction import (
    ConversationHistoryCompactor,
    DEFAULT_EVENTS_COMPACTION_CONFIG,
    EventsCompactionConfig,
    estimate_token_count,
    history_compactor,
)
from pressbox_war_room.memory.persistent_store import (
    DEFAULT_DATABASE_URL,
    DEFAULT_SQLITE_PATH,
    SQLiteScoutingMemoryDatabase,
    create_persistent_adk_session_service,
    persistent_memory_db,
)

__all__ = [
    "AsyncBackgroundMemoryManager",
    "ConversationHistoryCompactor",
    "DEFAULT_DATABASE_URL",
    "DEFAULT_EVENTS_COMPACTION_CONFIG",
    "DEFAULT_SQLITE_PATH",
    "EventsCompactionConfig",
    "SQLiteScoutingMemoryDatabase",
    "background_memory_manager",
    "create_persistent_adk_session_service",
    "estimate_token_count",
    "history_compactor",
    "persistent_memory_db",
]
