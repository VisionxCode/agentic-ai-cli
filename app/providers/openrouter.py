from __future__ import annotations

import os
from typing import Any

from app.providers.settings import saved_openrouter_api_key


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def openrouter_setting(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value is None:
        return None
    return value.strip()


def openrouter_api_key() -> str | None:
    return openrouter_setting("OPENROUTER_API_KEY") or saved_openrouter_api_key()


def openrouter_temperature() -> float | None:
    value = openrouter_setting("OPENROUTER_TEMPERATURE")
    if not value:
        return None
    try:
        temperature = float(value)
    except ValueError as exc:
        raise ValueError("OPENROUTER_TEMPERATURE must be a number between 0.0 and 2.0") from exc
    if not 0.0 <= temperature <= 2.0:
        raise ValueError("OPENROUTER_TEMPERATURE must be between 0.0 and 2.0")
    return temperature


def openrouter_reasoning_extra_body() -> dict[str, Any] | None:
    reasoning: dict[str, Any] = {}
    enabled = _bool_setting("OPENROUTER_REASONING_ENABLED")
    if enabled is not None:
        reasoning["enabled"] = enabled

    effort = openrouter_setting("OPENROUTER_REASONING_EFFORT")
    if effort:
        normalized_effort = effort.lower()
        allowed_efforts = {"none", "minimal", "low", "medium", "high", "xhigh"}
        if normalized_effort not in allowed_efforts:
            allowed = ", ".join(sorted(allowed_efforts))
            raise ValueError(f"OPENROUTER_REASONING_EFFORT must be one of: {allowed}")
        reasoning["effort"] = normalized_effort

    exclude = _bool_setting("OPENROUTER_REASONING_EXCLUDE")
    if exclude is not None:
        reasoning["exclude"] = exclude

    if not reasoning:
        return None
    return {"reasoning": reasoning}


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


def openrouter_extra_body() -> dict[str, Any] | None:
    extra_body: dict[str, Any] = {}
    for settings in (
        openrouter_provider_extra_body(),
        openrouter_reasoning_extra_body(),
    ):
        if settings:
            extra_body.update(settings)
    return extra_body or None


def build_openrouter_model(model_name: str) -> tuple[Any, Any]:
    try:
        from agents import AsyncOpenAI, ModelSettings, OpenAIChatCompletionsModel
    except ModuleNotFoundError as exc:
        raise RuntimeError("Install the OpenAI Agents SDK package: openai-agents") from exc

    api_key = openrouter_api_key()
    if not api_key:
        raise RuntimeError(
            "OpenRouter is selected but OPENROUTER_API_KEY is not set. "
            "Run `python -m app.main provider select` or set OPENROUTER_API_KEY."
        )

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=openrouter_setting("OPENROUTER_BASE_URL", OPENROUTER_BASE_URL),
        default_headers={
            "HTTP-Referer": openrouter_setting("OPENROUTER_HTTP_REFERER", "http://localhost"),
            "X-Title": openrouter_setting("OPENROUTER_APP_TITLE", "IBM Hackathon Agent Workflow"),
        },
    )
    model = OpenAIChatCompletionsModel(model=model_name, openai_client=client)
    model_settings = ModelSettings(
        temperature=openrouter_temperature(),
        extra_body=openrouter_extra_body(),
    )
    return model, model_settings


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
