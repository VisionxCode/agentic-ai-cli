from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.config_loader import load_yaml_file


def _resolve_env_value(key: str, value: str) -> str | None:
    if value == key and key in os.environ:
        return os.environ[key]
    if value == key:
        return None
    return value


def load_mcp_stdio_servers(paths: list[Path]) -> list[Any]:
    try:
        from agents.mcp import MCPServerStdio
    except ModuleNotFoundError as exc:
        raise RuntimeError("Install the OpenAI Agents SDK package: openai-agents") from exc

    servers = []
    for path in paths:
        config = load_yaml_file(path)
        for name, server_config in (config.get("mcpServers") or {}).items():
            env = {}
            for key, value in dict(server_config.get("env", {})).items():
                resolved = _resolve_env_value(key, str(value))
                if resolved is not None:
                    env[key] = resolved

            if "MINIMAX_API_KEY" in server_config.get("env", {}) and not env.get("MINIMAX_API_KEY"):
                continue

            params: dict[str, Any] = {"command": server_config["command"]}
            if server_config.get("args"):
                params["args"] = list(server_config["args"])
            if env:
                params["env"] = env
            if server_config.get("cwd"):
                params["cwd"] = str((path.parent / server_config["cwd"]).resolve())

            servers.append(MCPServerStdio(params=params, cache_tools_list=True, name=name))
    return servers
