from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.providers.codex import build_codex_model
from app.providers.openrouter import (
    OPENROUTER_BASE_URL,
    build_openrouter_model,
    openrouter_extra_body,
    openrouter_provider_extra_body,
    openrouter_reasoning_extra_body,
    openrouter_setting,
    openrouter_temperature,
)
from app.providers.selection import ProviderName, resolve_provider


@dataclass(frozen=True)
class AgentRuntime:
    agent: Any
    runner: Any
    mcp_servers: list[Any]

    async def connect_mcp_servers(self) -> None:
        for server in self.mcp_servers:
            if getattr(server, "session", None) is None:
                await server.connect()

    async def cleanup_mcp_servers(self) -> None:
        for server in self.mcp_servers:
            if getattr(server, "session", None) is not None:
                await server.cleanup()


def agent_max_turns(default: int = 30) -> int:
    value = openrouter_setting("OPENROUTER_AGENT_MAX_TURNS")
    if not value:
        return default
    try:
        return max(1, int(value))
    except ValueError:
        return default


def agent_finish_turns(default: int = 5) -> int:
    value = openrouter_setting("OPENROUTER_AGENT_FINISH_TURNS")
    if not value:
        return default
    try:
        return max(1, int(value))
    except ValueError:
        return default


def build_agent_runtime(
    *,
    name: str,
    instructions: str,
    model_name: str,
    provider: ProviderName | str | None = None,
    tools: list[Any] | None = None,
    mcp_servers: list[Any] | None = None,
) -> AgentRuntime:
    try:
        from agents import Agent, Runner, set_tracing_disabled
    except ModuleNotFoundError as exc:
        raise RuntimeError("Install the OpenAI Agents SDK package: openai-agents") from exc

    set_tracing_disabled(disabled=True)
    resolved_provider = resolve_provider(str(provider) if provider else None)
    if resolved_provider == "openrouter":
        model, model_settings = build_openrouter_model(model_name)
    elif resolved_provider == "codex":
        model, model_settings = build_codex_model(model_name)
    else:
        raise ValueError(f"Unsupported AI provider: {resolved_provider}")

    resolved_mcp_servers = mcp_servers or []
    return AgentRuntime(
        agent=Agent(
            name=name,
            instructions=instructions,
            model=model,
            model_settings=model_settings,
            tools=tools or [],
            mcp_servers=resolved_mcp_servers,
        ),
        runner=Runner,
        mcp_servers=resolved_mcp_servers,
    )


def build_openrouter_agent(
    *,
    name: str,
    instructions: str,
    model_name: str,
    tools: list[Any] | None = None,
    mcp_servers: list[Any] | None = None,
) -> AgentRuntime:
    return build_agent_runtime(
        name=name,
        instructions=instructions,
        model_name=model_name,
        provider="openrouter",
        tools=tools,
        mcp_servers=mcp_servers,
    )
