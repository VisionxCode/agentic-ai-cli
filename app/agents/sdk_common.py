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


def openrouter_provider_extra_body() -> dict[str, Any] | None:
    provider: dict[str, Any] = {}
    for key, env_name in {
        "order": "OPENROUTER_PROVIDER_ORDER",
        "only": "OPENROUTER_PROVIDER_ONLY",
        "ignore": "OPENROUTER_PROVIDER_IGNORE",
        "quantizations": "OPENROUTER_PROVIDER_QUANTIZATIONS",
    }.items():
        values = _csv_setting(env_name)
        if values:
            provider[key] = values

    for key, env_name in {
        "allow_fallbacks": "OPENROUTER_PROVIDER_ALLOW_FALLBACKS",
        "require_parameters": "OPENROUTER_PROVIDER_REQUIRE_PARAMETERS",
        "zdr": "OPENROUTER_PROVIDER_ZDR",
        "enforce_distillable_text": "OPENROUTER_PROVIDER_ENFORCE_DISTILLABLE_TEXT",
    }.items():
        value = _bool_setting(env_name)
        if value is not None:
            provider[key] = value

    data_collection = openrouter_setting("OPENROUTER_PROVIDER_DATA_COLLECTION")
    if data_collection:
        provider["data_collection"] = data_collection

    sort = openrouter_setting("OPENROUTER_PROVIDER_SORT")
    if sort:
        provider["sort"] = sort

    if not provider:
        return None
    return {"provider": provider}


def _csv_setting(name: str) -> list[str]:
    value = openrouter_setting(name)
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _bool_setting(name: str) -> bool | None:
    value = openrouter_setting(name)
    if not value:
        return None
    normalized = value.lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false when set")


def build_openrouter_agent(
    *,
    name: str,
    instructions: str,
    model_name: str,
    tools: list[Any] | None = None,
    mcp_servers: list[Any] | None = None,
) -> AgentRuntime:
    try:
        from agents import Agent, AsyncOpenAI, ModelSettings, OpenAIChatCompletionsModel, Runner, set_tracing_disabled
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
    provider_extra_body = openrouter_provider_extra_body()
    model_settings = (
        ModelSettings(extra_body=provider_extra_body) if provider_extra_body else ModelSettings()
    )
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
