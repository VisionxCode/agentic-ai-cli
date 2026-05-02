from __future__ import annotations

import os
from typing import Literal

from app.providers.settings import read_user_config


ProviderName = Literal["openrouter", "codex"]
PROVIDER_NAMES: set[str] = {"openrouter", "codex"}


def normalize_provider(value: str | None) -> ProviderName:
    normalized = (value or "").strip().lower()
    if normalized in {"openai-codex", "openai_codex"}:
        normalized = "codex"
    if normalized not in PROVIDER_NAMES:
        allowed = ", ".join(sorted(PROVIDER_NAMES))
        raise ValueError(f"AI provider must be one of: {allowed}")
    return normalized  # type: ignore[return-value]


def resolve_provider(cli_provider: str | None = None) -> ProviderName:
    if cli_provider:
        return normalize_provider(cli_provider)

    config = read_user_config()
    saved_provider = config.get("provider")
    if isinstance(saved_provider, str) and saved_provider.strip():
        return normalize_provider(saved_provider)

    env_provider = os.getenv("AI_PROVIDER")
    if env_provider:
        return normalize_provider(env_provider)

    return "openrouter"
