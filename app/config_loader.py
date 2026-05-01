from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AgentProfile:
    name: str
    instructions: str
    tool_names: list[str]
    skill_paths: list[Path]
    mcp_config_paths: list[Path]


def _strip_yaml_comments(line: str) -> str:
    in_quote = False
    quote_char = ""
    for index, char in enumerate(line):
        if char in {"'", '"'} and (index == 0 or line[index - 1] != "\\"):
            if in_quote and char == quote_char:
                in_quote = False
            elif not in_quote:
                in_quote = True
                quote_char = char
        if char == "#" and not in_quote:
            return line[:index]
    return line


def _coerce_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "false"}:
        return value == "true"
    if value in {"null", "None", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _coerce_env_value(value: str) -> str:
    value = value.strip()
    if value.startswith("export "):
        value = value.removeprefix("export ").strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def load_env_file(project_root: Path, filename: str = ".env") -> None:
    path = project_root / filename
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            os.environ.setdefault(key, _coerce_env_value(value))


def load_yaml_file(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    except ModuleNotFoundError:
        return _load_limited_yaml(path)


def _load_limited_yaml(path: Path) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]
    pending_key: tuple[int, dict[str, Any], str] | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = _strip_yaml_comments(raw_line).rstrip()
        if not line.strip():
            continue

        indent = len(line) - len(line.lstrip(" "))
        text = line.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()

        if text.startswith("- "):
            if pending_key is not None:
                pending_indent, pending_parent, key = pending_key
                if pending_indent < indent:
                    pending_parent[key] = []
                    stack.append((pending_indent + 1, pending_parent[key]))
                pending_key = None
            current = stack[-1][1]
            if not isinstance(current, list):
                raise ValueError(f"Unsupported YAML list placement in {path}: {raw_line}")
            current.append(_coerce_scalar(text[2:]))
            continue

        key, _, value = text.partition(":")
        current = stack[-1][1]
        if not isinstance(current, dict):
            raise ValueError(f"Unsupported YAML mapping placement in {path}: {raw_line}")

        if value.strip():
            current[key] = _coerce_scalar(value)
            pending_key = None
        else:
            current[key] = {}
            pending_key = (indent, current, key)
            stack.append((indent, current[key]))

    return root


def _read_joined(paths: list[Path]) -> str:
    sections = []
    for path in paths:
        sections.append(path.read_text(encoding="utf-8").strip())
    return "\n\n".join(section for section in sections if section)


def load_agent_profile(project_root: Path, agent_name: str) -> AgentProfile:
    registry = load_yaml_file(project_root / "config" / "agent_registry.yaml")
    try:
        config = registry["agents"][agent_name]
    except KeyError as exc:
        raise KeyError(f"Agent profile '{agent_name}' is not defined") from exc

    instruction_paths = [project_root / item for item in config.get("instructions", [])]
    skill_paths = [project_root / item for item in config.get("skills", [])]
    mcp_config_paths = [project_root / item for item in config.get("mcp_servers", [])]
    instructions = _read_joined(instruction_paths + skill_paths)

    return AgentProfile(
        name=agent_name,
        instructions=instructions,
        tool_names=list(config.get("tools", [])),
        skill_paths=skill_paths,
        mcp_config_paths=mcp_config_paths,
    )


def load_models(project_root: Path) -> dict[str, str]:
    config = load_yaml_file(project_root / "config" / "models.yaml")
    models = dict(config.get("models", config))
    shared_model = os.getenv("OPENROUTER_MODEL")
    if shared_model:
        models["coder"] = shared_model
        models["evaluator"] = shared_model
    if os.getenv("OPENROUTER_CODER_MODEL"):
        models["coder"] = os.environ["OPENROUTER_CODER_MODEL"]
    if os.getenv("OPENROUTER_EVALUATOR_MODEL"):
        models["evaluator"] = os.environ["OPENROUTER_EVALUATOR_MODEL"]
    return models


def load_thresholds(project_root: Path) -> dict[str, Any]:
    return load_yaml_file(project_root / "config" / "thresholds.yaml")
