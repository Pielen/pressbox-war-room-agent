"""ADK compatibility layer for PressBox War Room.

Uses the official `google.adk` SDK in production and ADK evaluation environments,
while providing an API-compatible fallback for hermetic unit test environments
where `google-adk` may not be pre-installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional
import uuid

try:
    from google.adk.agents import (  # type: ignore[import-untyped]
        BaseAgent,
        LlmAgent,
        LoopAgent,
        ParallelAgent,
        SequentialAgent,
    )
    from google.adk.memory import InMemoryMemoryService  # type: ignore[import-untyped]
    from google.adk.runners import Runner  # type: ignore[import-untyped]
    from google.adk.sessions import InMemorySessionService  # type: ignore[import-untyped]
    from google.adk.tools import (  # type: ignore[import-untyped]
        FunctionTool,
        ToolContext,
        exit_loop,
    )

    ADK_AVAILABLE = True

except ImportError:
    ADK_AVAILABLE = False

    @dataclass
    class EventActions:
        """Models ADK EventActions (`tool_context.actions.escalate = True`)."""

        escalate: bool = False
        transfer_to_agent: Optional[str] = None
        state_delta: dict[str, Any] = field(default_factory=dict)

    class ToolContext:
        """Compatible ADK ToolContext with session `.state` and `.actions`."""

        def __init__(
            self,
            state: Optional[dict[str, Any]] = None,
            agent_name: str = "WarRoomAgent",
            invocation_id: Optional[str] = None,
        ) -> None:
            self.state: dict[str, Any] = state if state is not None else {}
            self.agent_name: str = agent_name
            self.invocation_id: str = invocation_id or f"inv-{uuid.uuid4().hex[:8]}"
            self.actions: EventActions = EventActions()

    class FunctionTool:
        """Wraps a Python callable as an ADK FunctionTool."""

        def __init__(self, func: Callable[..., Any]) -> None:
            self.func = func
            self.name = getattr(func, "__name__", "tool")
            self.description = getattr(func, "__doc__", "") or ""

        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            return self.func(*args, **kwargs)

    def exit_loop(tool_context: ToolContext) -> dict[str, Any]:
        """Standard ADK built-in tool to exit a LoopAgent."""
        tool_context.actions.escalate = True
        return {"status": "exited_loop", "escalate": True}

    class BaseAgent:
        """Compatible base class for ADK agents."""

        def __init__(
            self,
            name: str,
            description: str = "",
            sub_agents: Optional[list[Any]] = None,
            before_agent_callback: Optional[Callable[..., Any]] = None,
            after_agent_callback: Optional[Callable[..., Any]] = None,
        ) -> None:
            self.name = name
            self.description = description
            self.sub_agents = list(sub_agents or [])
            self.before_agent_callback = before_agent_callback
            self.after_agent_callback = after_agent_callback

    class LlmAgent(BaseAgent):
        """Compatible ADK LlmAgent."""

        def __init__(
            self,
            name: str,
            model: str = "gemini-2.5-flash",
            description: str = "",
            instruction: str = "",
            tools: Optional[list[Any]] = None,
            sub_agents: Optional[list[Any]] = None,
            output_key: Optional[str] = None,
            before_agent_callback: Optional[Callable[..., Any]] = None,
            after_agent_callback: Optional[Callable[..., Any]] = None,
            before_model_callback: Optional[Callable[..., Any]] = None,
            after_model_callback: Optional[Callable[..., Any]] = None,
            before_tool_callback: Optional[Callable[..., Any]] = None,
            after_tool_callback: Optional[Callable[..., Any]] = None,
        ) -> None:
            super().__init__(
                name=name,
                description=description,
                sub_agents=sub_agents,
                before_agent_callback=before_agent_callback,
                after_agent_callback=after_agent_callback,
            )
            self.model = model
            self.instruction = instruction
            self.tools = list(tools or [])
            self.output_key = output_key
            self.before_model_callback = before_model_callback
            self.after_model_callback = after_model_callback
            self.before_tool_callback = before_tool_callback
            self.after_tool_callback = after_tool_callback

    class ParallelAgent(BaseAgent):
        """Compatible ADK ParallelAgent that runs sub-agents concurrently."""

        def __init__(
            self,
            name: str,
            description: str = "",
            sub_agents: Optional[list[Any]] = None,
            before_agent_callback: Optional[Callable[..., Any]] = None,
            after_agent_callback: Optional[Callable[..., Any]] = None,
        ) -> None:
            super().__init__(
                name=name,
                description=description,
                sub_agents=sub_agents,
                before_agent_callback=before_agent_callback,
                after_agent_callback=after_agent_callback,
            )

    class SequentialAgent(BaseAgent):
        """Compatible ADK SequentialAgent that executes sub-agents in order."""

        def __init__(
            self,
            name: str,
            description: str = "",
            sub_agents: Optional[list[Any]] = None,
            before_agent_callback: Optional[Callable[..., Any]] = None,
            after_agent_callback: Optional[Callable[..., Any]] = None,
        ) -> None:
            super().__init__(
                name=name,
                description=description,
                sub_agents=sub_agents,
                before_agent_callback=before_agent_callback,
                after_agent_callback=after_agent_callback,
            )

    class LoopAgent(BaseAgent):
        """Compatible ADK LoopAgent that iterates until max_iterations or escalate."""

        def __init__(
            self,
            name: str,
            description: str = "",
            sub_agents: Optional[list[Any]] = None,
            max_iterations: int = 2,
            before_agent_callback: Optional[Callable[..., Any]] = None,
            after_agent_callback: Optional[Callable[..., Any]] = None,
        ) -> None:
            super().__init__(
                name=name,
                description=description,
                sub_agents=sub_agents,
                before_agent_callback=before_agent_callback,
                after_agent_callback=after_agent_callback,
            )
            self.max_iterations = max_iterations

    class InMemorySessionService:
        """Compatible ADK InMemorySessionService for session state persistence."""

        def __init__(self) -> None:
            self._sessions: dict[tuple[str, str, str], dict[str, Any]] = {}

        def create_session_sync(
            self,
            app_name: str,
            user_id: str,
            session_id: Optional[str] = None,
            state: Optional[dict[str, Any]] = None,
        ) -> dict[str, Any]:
            sid = session_id or f"session-{uuid.uuid4().hex[:8]}"
            session_obj = {
                "app_name": app_name,
                "user_id": user_id,
                "id": sid,
                "state": dict(state or {}),
            }
            self._sessions[(app_name, user_id, sid)] = session_obj
            return session_obj

        def get_session_sync(
            self, app_name: str, user_id: str, session_id: str
        ) -> Optional[dict[str, Any]]:
            return self._sessions.get((app_name, user_id, session_id))

    class InMemoryMemoryService:
        """Compatible ADK InMemoryMemoryService for cross-session search."""

        def __init__(self) -> None:
            self._memories: list[dict[str, Any]] = []

        def add_session_to_memory(self, session: dict[str, Any]) -> None:
            self._memories.append(dict(session))

        def search_memory(
            self, app_name: str, user_id: str, query: str
        ) -> list[dict[str, Any]]:
            q = query.lower()
            return [
                m
                for m in self._memories
                if m.get("app_name") == app_name
                and m.get("user_id") == user_id
                and q in str(m.get("state", "")).lower()
            ]

    class Runner:
        """Compatible ADK Runner binding agent, session service, and memory service."""

        def __init__(
            self,
            agent: BaseAgent,
            app_name: str,
            session_service: InMemorySessionService,
            memory_service: Optional[InMemoryMemoryService] = None,
        ) -> None:
            self.agent = agent
            self.app_name = app_name
            self.session_service = session_service
            self.memory_service = memory_service or InMemoryMemoryService()

__all__ = [
    "ADK_AVAILABLE",
    "BaseAgent",
    "FunctionTool",
    "InMemoryMemoryService",
    "InMemorySessionService",
    "LlmAgent",
    "LoopAgent",
    "ParallelAgent",
    "Runner",
    "SequentialAgent",
    "ToolContext",
    "exit_loop",
]
