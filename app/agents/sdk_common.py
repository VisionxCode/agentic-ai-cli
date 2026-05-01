from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


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


def openrouter_setting(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value is None:
        return None
    return value.strip()


def agent_max_turns(default: int = 30) -> int:
    value = openrouter_setting("OPENROUTER_AGENT_MAX_TURNS")
    if not value:
        return default
    try:
        return max(1, int(value))
    except ValueError:
        return default


def build_openrouter_agent(
    *,
    name: str,
    instructions: str,
    model_name: str,
    tools: list[Any] | None = None,
    mcp_servers: list[Any] | None = None,
) -> AgentRuntime:
    try:
        from agents import Agent, AsyncOpenAI, OpenAIChatCompletionsModel, Runner, set_tracing_disabled
    except ModuleNotFoundError as exc:
        raise RuntimeError("Install the OpenAI Agents SDK package: openai-agents") from exc

    api_key = openrouter_setting("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY must be set to use OpenRouter models")

    set_tracing_disabled(disabled=True)
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=openrouter_setting("OPENROUTER_BASE_URL", OPENROUTER_BASE_URL),
        default_headers={
            "HTTP-Referer": openrouter_setting("OPENROUTER_HTTP_REFERER", "http://localhost"),
            "X-Title": openrouter_setting("OPENROUTER_APP_TITLE", "IBM Hackathon Agent Workflow"),
        },
    )
    model = OpenAIChatCompletionsModel(model=model_name, openai_client=client)
    resolved_mcp_servers = mcp_servers or []
    return AgentRuntime(
        agent=Agent(
            name=name,
            instructions=instructions,
            model=model,
            tools=tools or [],
            mcp_servers=resolved_mcp_servers,
        ),
        runner=Runner,
        mcp_servers=resolved_mcp_servers,
    )
