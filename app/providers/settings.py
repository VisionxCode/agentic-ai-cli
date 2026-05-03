from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


APP_HOME_ENV = "AGENTIC_AI_CLI_HOME"
LEGACY_APP_HOME_ENV = "IBM_HACKATHON_AGENT_HOME"
CONFIG_ENV = "AGENTIC_AI_CLI_CONFIG"
LEGACY_CONFIG_ENV = "IBM_HACKATHON_AGENT_CONFIG"
DEFAULT_APP_HOME = ".agentic_ai_cli"
CONFIG_FILENAME = "config.json"


def _first_env_value(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def app_home() -> Path:
    configured = _first_env_value(APP_HOME_ENV, LEGACY_APP_HOME_ENV)
    if configured:
        return Path(configured).expanduser()
    return Path.home() / DEFAULT_APP_HOME


def user_config_path() -> Path:
    configured = _first_env_value(CONFIG_ENV, LEGACY_CONFIG_ENV)
    if configured:
        return Path(configured).expanduser()
    return app_home() / CONFIG_FILENAME


def read_user_config() -> dict[str, Any]:
    if os.environ.get("PYTEST_CURRENT_TEST") and not (
        os.getenv(APP_HOME_ENV)
        or os.getenv(LEGACY_APP_HOME_ENV)
        or os.getenv(CONFIG_ENV)
        or os.getenv(LEGACY_CONFIG_ENV)
    ):
        return {}
    path = user_config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Could not read provider config at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Provider config at {path} must be a JSON object")
    return data


def write_user_config(config: dict[str, Any]) -> Path:
    path = user_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(config, indent=2, sort_keys=True) + "\n"
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(payload, encoding="utf-8")
    temp_path.replace(path)
    return path


def save_active_provider(provider: str) -> Path:
    config = read_user_config()
    config["provider"] = provider
    return write_user_config(config)


def save_provider_models(provider: str, models: dict[str, str]) -> Path:
    config = read_user_config()
    all_models = config.setdefault("models", {})
    if not isinstance(all_models, dict):
        all_models = {}
        config["models"] = all_models
    all_models[provider] = {key: value for key, value in models.items() if value}
    return write_user_config(config)


def provider_models(provider: str) -> dict[str, str]:
    config = read_user_config()
    models = config.get("models")
    if not isinstance(models, dict):
        return {}
    provider_config = models.get(provider)
    if not isinstance(provider_config, dict):
        return {}
    return {
        str(key): str(value).strip()
        for key, value in provider_config.items()
        if isinstance(value, str) and value.strip()
    }


def save_openrouter_api_key(api_key: str) -> Path:
    config = read_user_config()
    credentials = config.setdefault("credentials", {})
    if not isinstance(credentials, dict):
        credentials = {}
        config["credentials"] = credentials
    credentials["openrouter"] = {"api_key": api_key.strip()}
    return write_user_config(config)


def saved_openrouter_api_key() -> str | None:
    config = read_user_config()
    credentials = config.get("credentials")
    if not isinstance(credentials, dict):
        return None
    openrouter = credentials.get("openrouter")
    if not isinstance(openrouter, dict):
        return None
    value = openrouter.get("api_key")
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
