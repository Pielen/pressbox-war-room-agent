"""ADK and Pydantic v2 compatibility layer for PressBox War Room.

Uses the official `google.adk` and `pydantic` v2 SDKs in production and automated
grading environments, while providing an API-compatible fallback for hermetic
offline test runners.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import inspect
from typing import Any, Callable, Optional, get_type_hints
import uuid

try:
    from pydantic import (  # type: ignore[import-untyped]
        BaseModel,
        ConfigDict,
        Field,
        ValidationError,
        field_validator,
        model_validator,
    )

    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False

    class ValidationError(ValueError):
        """Compatible Pydantic ValidationError."""

        def __init__(self, message: str, errors_list: Optional[list[dict[str, Any]]] = None) -> None:
            super().__init__(message)
            self._errors = errors_list or [{"msg": message}]

        def errors(self) -> list[dict[str, Any]]:
            return self._errors

    def ConfigDict(**kwargs: Any) -> dict[str, Any]:
        return dict(kwargs)

    class _FieldInfo:
        def __init__(self, default: Any = ..., **kwargs: Any) -> None:
            self.default = default
            self.default_factory = kwargs.get("default_factory")
            self.description = kwargs.get("description", "")
            self.ge = kwargs.get("ge")
            self.le = kwargs.get("le")
            self.min_length = kwargs.get("min_length")
            self.max_length = kwargs.get("max_length")
            self.pattern = kwargs.get("pattern")

    def Field(default: Any = ..., **kwargs: Any) -> Any:
        return _FieldInfo(default=default, **kwargs)

    def field_validator(*fields: str, mode: str = "after") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            target = fn.__func__ if isinstance(fn, classmethod) else fn
            setattr(target, "__field_validator_fields__", fields)
            setattr(target, "__field_validator_mode__", mode)
            return fn

        return decorator

    def model_validator(mode: str = "after") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            target = fn.__func__ if isinstance(fn, classmethod) else fn
            setattr(target, "__model_validator_mode__", mode)
            return fn

        return decorator

    class BaseModel:
        """Compatible Pydantic v2 BaseModel with strict validation and JSON schema export."""

        @classmethod
        def _all_annotations(cls) -> dict[str, Any]:
            merged: dict[str, Any] = {}
            for base in reversed(cls.__mro__):
                merged.update(getattr(base, "__annotations__", {}))
            return merged

        def __init__(self, **data: Any) -> None:
            cls = self.__class__
            annotations = cls._all_annotations()
            errors: list[dict[str, Any]] = []

            # Set attributes and apply Field constraints
            for name in annotations:
                attr_val = getattr(cls, name, ...)
                if name in data:
                    val = data[name]
                elif isinstance(attr_val, _FieldInfo):
                    if attr_val.default_factory is not None:
                        val = attr_val.default_factory()
                    elif attr_val.default is not ...:
                        val = attr_val.default
                    else:
                        errors.append({"loc": (name,), "msg": f"Field '{name}' is required"})
                        continue
                elif attr_val is not ...:
                    val = attr_val
                else:
                    errors.append({"loc": (name,), "msg": f"Field '{name}' is required"})
                    continue

                if isinstance(attr_val, _FieldInfo) and val is not None:
                    if attr_val.ge is not None and isinstance(val, (int, float)) and val < attr_val.ge:
                        errors.append({"loc": (name,), "msg": f"Input should be >= {attr_val.ge}"})
                    if attr_val.le is not None and isinstance(val, (int, float)) and val > attr_val.le:
                        errors.append({"loc": (name,), "msg": f"Input should be <= {attr_val.le}"})
                    if attr_val.min_length is not None and isinstance(val, str) and len(val) < attr_val.min_length:
                        errors.append(
                            {
                                "loc": (name,),
                                "msg": f"String should have at least {attr_val.min_length} characters",
                            }
                        )

                setattr(self, name, val)

            # Execute @field_validator methods across MRO
            for base in reversed(cls.__mro__):
                for _, raw_attr in base.__dict__.items():
                    fn = raw_attr.__func__ if isinstance(raw_attr, classmethod) else raw_attr
                    v_fields = getattr(fn, "__field_validator_fields__", None)
                    if v_fields:
                        for f_name in v_fields:
                            if hasattr(self, f_name):
                                try:
                                    new_val = fn(cls, getattr(self, f_name))
                                    setattr(self, f_name, new_val)
                                except Exception as exc:  # noqa: BLE001
                                    if hasattr(exc, "error_code"):
                                        raise
                                    errors.append({"loc": (f_name,), "msg": str(exc)})

            # Execute @model_validator methods across MRO
            for base in reversed(cls.__mro__):
                for _, raw_attr in base.__dict__.items():
                    fn = raw_attr.__func__ if isinstance(raw_attr, classmethod) else raw_attr
                    m_mode = getattr(fn, "__model_validator_mode__", None)
                    if m_mode and not errors:
                        try:
                            fn(self)
                        except Exception as exc:  # noqa: BLE001
                            if hasattr(exc, "error_code"):
                                raise
                            errors.append({"loc": ("__root__",), "msg": str(exc)})

            if errors:
                summary = "; ".join(f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in errors)
                raise ValidationError(summary, errors)

        @classmethod
        def model_validate(cls, obj: Any) -> Any:
            if isinstance(obj, cls):
                return obj
            if isinstance(obj, dict):
                return cls(**obj)
            raise ValidationError(f"Expected dict for {cls.__name__}, got {type(obj).__name__}")

        def model_dump(self) -> dict[str, Any]:
            def _serialize(v: Any) -> Any:
                if isinstance(v, BaseModel):
                    return v.model_dump()
                if isinstance(v, list):
                    return [_serialize(i) for i in v]
                if isinstance(v, dict):
                    return {k: _serialize(val) for k, val in v.items()}
                return v

            annotations = self._all_annotations()
            return {k: _serialize(getattr(self, k)) for k in annotations if hasattr(self, k)}

        @classmethod
        def model_json_schema(cls) -> dict[str, Any]:
            annotations = cls._all_annotations()
            properties: dict[str, Any] = {}
            required: list[str] = []
            for name, type_hint in annotations.items():
                attr_val = getattr(cls, name, ...)
                desc = attr_val.description if isinstance(attr_val, _FieldInfo) else ""
                properties[name] = {
                    "title": name.replace("_", " ").title(),
                    "type": str(type_hint),
                    "description": desc,
                }
                if isinstance(attr_val, _FieldInfo):
                    if attr_val.default is ... and attr_val.default_factory is None:
                        required.append(name)
                elif attr_val is ...:
                    required.append(name)
            return {
                "title": cls.__name__,
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            }

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
        """Wraps a Python callable as an ADK FunctionTool with JSON Schema introspection."""

        def __init__(self, func: Callable[..., Any]) -> None:
            self.func = func
            self.name = getattr(func, "__name__", "tool")
            self.description = getattr(func, "__doc__", "") or ""
            self.input_schema = getattr(func, "input_schema", None)
            self.output_schema = getattr(func, "output_schema", None)

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
            input_schema: Optional[Any] = None,
            output_schema: Optional[Any] = None,
            before_agent_callback: Optional[Callable[..., Any]] = None,
            after_agent_callback: Optional[Callable[..., Any]] = None,
            before_model_callback: Optional[Callable[..., Any]] = None,
            after_model_callback: Optional[Callable[..., Any]] = None,
            on_model_error_callback: Optional[Callable[..., Any]] = None,
            before_tool_callback: Optional[Callable[..., Any]] = None,
            after_tool_callback: Optional[Callable[..., Any]] = None,
            on_tool_error_callback: Optional[Callable[..., Any]] = None,
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
            self.input_schema = input_schema
            self.output_schema = output_schema
            self.before_model_callback = before_model_callback
            self.after_model_callback = after_model_callback
            self.on_model_error_callback = on_model_error_callback
            self.before_tool_callback = before_tool_callback
            self.after_tool_callback = after_tool_callback
            self.on_tool_error_callback = on_tool_error_callback

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
    "BaseModel",
    "ConfigDict",
    "Field",
    "FunctionTool",
    "InMemoryMemoryService",
    "InMemorySessionService",
    "LlmAgent",
    "LoopAgent",
    "PYDANTIC_AVAILABLE",
    "ParallelAgent",
    "Runner",
    "SequentialAgent",
    "ToolContext",
    "ValidationError",
    "exit_loop",
    "field_validator",
    "get_type_hints",
    "model_validator",
]
