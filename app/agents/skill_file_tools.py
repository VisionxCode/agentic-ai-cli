from __future__ import annotations

from pathlib import Path

from app.job_logging import log_tool_usage


def _resolve_skill_root(skills_root: Path, skill_name: str) -> Path:
    root = skills_root.resolve()
    safe_name = skill_name.replace("-", "_")
    skill_root = (root / safe_name).resolve()
    if not skill_root.is_dir() or not skill_root.is_relative_to(root):
        raise ValueError(f"Unknown skill: {skill_name}")
    return skill_root


def _resolve_skill_file(skills_root: Path, skill_name: str, relative_path: str) -> Path:
    skill_root = _resolve_skill_root(skills_root, skill_name)
    target = (skill_root / relative_path).resolve()
    if not target.is_file() or not target.is_relative_to(skill_root):
        raise ValueError(f"Skill file is not readable: {relative_path}")
    return target


def list_skill_files_for_root(
    skills_root: Path, skill_name: str, relative_dir: str = "."
) -> list[str]:
    skill_root = _resolve_skill_root(skills_root, skill_name)
    target_dir = (skill_root / relative_dir).resolve()
    if not target_dir.is_dir() or not target_dir.is_relative_to(skill_root):
        raise ValueError(f"Skill directory is not readable: {relative_dir}")

    files = [
        str(path.relative_to(skill_root)).replace("\\", "/")
        for path in sorted(target_dir.rglob("*"))
        if path.is_file()
    ]
    log_tool_usage(
        "list_skill_files",
        skill=skill_name,
        path=target_dir,
        matches=len(files),
    )
    return files


def read_skill_file_for_root(
    skills_root: Path, skill_name: str, relative_path: str, max_chars: int = 30000
) -> str:
    target = _resolve_skill_file(skills_root, skill_name, relative_path)
    content = target.read_text(encoding="utf-8")
    limit = max(1, int(max_chars))
    truncated = len(content) > limit
    log_tool_usage(
        "read_skill_file",
        skill=skill_name,
        path=target,
        chars=min(len(content), limit),
        truncated=truncated,
    )
    if truncated:
        return content[:limit] + "\n\n[truncated: request a smaller file or lower max_chars]"
    return content


def build_skill_file_tools(skills_root: Path) -> list:
    try:
        from agents import function_tool
    except ModuleNotFoundError as exc:
        raise RuntimeError("Install the OpenAI Agents SDK package: openai-agents") from exc

    root = skills_root.resolve()

    @function_tool
    def list_skill_files(skill_name: str, relative_dir: str = ".") -> list[str]:
        """List files inside a project skill folder, such as huashu_design."""
        return list_skill_files_for_root(root, skill_name, relative_dir)

    @function_tool
    def read_skill_file(skill_name: str, relative_path: str, max_chars: int = 30000) -> str:
        """Read a text file from a project skill folder. Use this for bundled skill references."""
        return read_skill_file_for_root(root, skill_name, relative_path, max_chars)

    return [list_skill_files, read_skill_file]
