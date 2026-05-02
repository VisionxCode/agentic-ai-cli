from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.agents.coder_prompts import (
    build_coder_dynamic_context,
    build_coder_static_prompt,
    build_complete_html_fallback_prompt,
)
from app.agents.html_file_tools import build_html_file_tools
from app.agents.image_inputs import image_input_from_path, text_input, user_message_with_content
from app.agents.sdk_common import (
    AgentRuntime,
    agent_finish_turns,
    agent_max_turns,
    build_agent_runtime,
)
from app.agents.skill_file_tools import build_skill_file_tools
from app.job_logging import current_job_logger
from app.mcp_loader import load_mcp_stdio_servers


APP_ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)

CODER_TOOL_NAMES = [
    "read_html_file",
    "search_html_file",
    "read_html_lines",
    "replace_html_lines",
    "insert_html_after_line",
    "write_html_file",
    "list_source_files",
    "read_text_file",
    "write_text_file",
    "list_skill_files",
    "read_skill_file",
]


class CoderAgentClient:
    def __init__(
        self,
        runtime: AgentRuntime | None = None,
        *,
        instructions: str | None = None,
        model_name: str | None = None,
        provider: str | None = None,
        mcp_config_paths: list[Path] | None = None,
    ) -> None:
        self.runtime = runtime
        self.instructions = instructions
        self.model_name = model_name
        self.provider = provider
        self.mcp_config_paths = mcp_config_paths or []

    @classmethod
    def from_config(
        cls,
        *,
        instructions: str,
        model_name: str,
        provider: str | None = None,
        mcp_config_paths: list[Path] | None = None,
    ) -> "CoderAgentClient":
        return cls(
            instructions=instructions,
            model_name=model_name,
            provider=provider,
            mcp_config_paths=mcp_config_paths or [],
        )

    async def generate_html(
        self,
        *,
        original_image_path: Path,
        source_path: Path,
        current_source: str | None,
        previous_evaluation: dict[str, Any] | None,
        iteration_number: int,
        previous_screenshot_path: Path | None,
        user_note: str | None,
    ) -> str:
        source_exists = source_path.exists()
        source_root = source_path.parent
        runtime = self._runtime_for_source_root(source_root)
        static_prompt = build_coder_static_prompt()
        dynamic_context = build_coder_dynamic_context(
            iteration_number=iteration_number,
            source_exists=source_exists,
            source_manifest=_source_manifest(source_root),
            previous_evaluation=previous_evaluation,
            user_note=_clean_user_note(user_note),
            previous_screenshot_path=previous_screenshot_path,
        )
        content = [
            text_input(static_prompt),
            image_input_from_path(original_image_path, detail="high"),
            text_input(dynamic_context),
        ]
        if previous_screenshot_path is not None:
            content.append(image_input_from_path(previous_screenshot_path, detail="high"))
        input_items = user_message_with_content(content)
        connect_mcp_servers = getattr(runtime, "connect_mcp_servers", None)
        if connect_mcp_servers is not None:
            await connect_mcp_servers()
        try:
            result = await self._run_with_tool_error_retry(
                runtime=runtime,
                input_items=input_items,
                original_prompt={
                    "static_prompt": static_prompt,
                    "dynamic_context": dynamic_context,
                },
            )
        finally:
            cleanup_mcp_servers = getattr(runtime, "cleanup_mcp_servers", None)
            if cleanup_mcp_servers is not None:
                await cleanup_mcp_servers()
        output = str(result.final_output).strip()
        _log_info(
            "Coder primary output: chars=%d source_exists=%s preview=%s",
            len(output),
            source_path.exists(),
            _one_line_preview(output),
        )
        if output.lower().startswith("<!doctype") or output.lower().startswith("<html"):
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_text(output, encoding="utf-8")
        elif not source_path.exists() or not output:
            fallback_output = await self._run_complete_html_fallback(
                runtime=runtime,
                source_path=source_path,
                original_image_path=original_image_path,
                previous_screenshot_path=previous_screenshot_path,
                previous_output=output,
                current_source=current_source,
                previous_evaluation=previous_evaluation,
                iteration_number=iteration_number,
                user_note=user_note,
            )
            _log_info(
                "Coder fallback output: chars=%d preview=%s",
                len(fallback_output),
                _one_line_preview(fallback_output),
            )
            if fallback_output.lower().startswith(("<!doctype", "<html")):
                source_path.parent.mkdir(parents=True, exist_ok=True)
                source_path.write_text(fallback_output, encoding="utf-8")
        if source_path.exists():
            return source_path.read_text(encoding="utf-8").strip()
        return output

    async def _run_complete_html_fallback(
        self,
        *,
        runtime: AgentRuntime,
        source_path: Path,
        original_image_path: Path,
        previous_screenshot_path: Path | None,
        previous_output: str,
        current_source: str | None,
        previous_evaluation: dict[str, Any] | None,
        iteration_number: int,
        user_note: str | None,
    ) -> str:
        fallback_runtime = self._fallback_runtime_without_tools(runtime)
        prompt = build_complete_html_fallback_prompt(
            previous_output=previous_output,
            current_source=current_source,
            previous_evaluation=previous_evaluation,
            iteration_number=iteration_number,
            user_note=_clean_user_note(user_note),
        )
        content = [
            text_input(prompt),
            image_input_from_path(original_image_path, detail="high"),
        ]
        if previous_screenshot_path is not None:
            content.append(image_input_from_path(previous_screenshot_path, detail="high"))
        result = await fallback_runtime.runner.run(
            fallback_runtime.agent,
            user_message_with_content(content),
            max_turns=agent_finish_turns(default=3),
        )
        return str(result.final_output).strip()

    def _fallback_runtime_without_tools(self, runtime: AgentRuntime) -> AgentRuntime:
        if self.runtime is not None or self.instructions is None or self.model_name is None:
            return runtime
        return build_agent_runtime(
            name="coder_html_fallback",
            instructions=self.instructions,
            model_name=self.model_name,
            provider=self.provider,
        )

    async def _run_with_tool_error_retry(
        self,
        *,
        runtime: AgentRuntime,
        input_items: list[dict[str, Any]],
        original_prompt: dict[str, Any],
    ):
        try:
            return await runtime.runner.run(
                runtime.agent,
                input_items,
                max_turns=agent_max_turns(),
            )
        except Exception as exc:
            if _is_agent_max_turns_exceeded(exc):
                finish_prompt = _finish_after_max_turns_prompt(original_prompt, exc)
                return await runtime.runner.run(
                    runtime.agent,
                    user_message_with_content([text_input(finish_prompt)]),
                    max_turns=agent_finish_turns(),
                )
            if not _is_model_behavior_error(exc):
                raise
            retry_prompt = _tool_error_retry_prompt(original_prompt, exc)
            try:
                return await runtime.runner.run(
                    runtime.agent,
                    user_message_with_content([text_input(retry_prompt)]),
                    max_turns=agent_max_turns(),
                )
            except Exception as retry_exc:
                if not _is_agent_max_turns_exceeded(retry_exc):
                    raise
                finish_prompt = _finish_after_max_turns_prompt(original_prompt, retry_exc)
                return await runtime.runner.run(
                    runtime.agent,
                    user_message_with_content([text_input(finish_prompt)]),
                    max_turns=agent_finish_turns(),
                )

    def _runtime_for_source_root(self, source_root: Path) -> AgentRuntime:
        if self.runtime is not None:
            return self.runtime
        if self.instructions is None or self.model_name is None:
            raise RuntimeError("CoderAgentClient requires a runtime or model configuration.")
        tools = [
            *build_html_file_tools(source_root=source_root),
            *build_skill_file_tools(APP_ROOT / "skills"),
        ]
        return build_agent_runtime(
            name="coder",
            instructions=self.instructions,
            model_name=self.model_name,
            provider=self.provider,
            tools=tools,
            mcp_servers=load_mcp_stdio_servers(self.mcp_config_paths),
        )


def _is_model_behavior_error(exc: Exception) -> bool:
    try:
        from agents.exceptions import ModelBehaviorError
    except ModuleNotFoundError:
        return False
    return isinstance(exc, ModelBehaviorError)


def _is_agent_max_turns_exceeded(exc: Exception) -> bool:
    try:
        from agents.exceptions import MaxTurnsExceeded
    except ModuleNotFoundError:
        return False
    return isinstance(exc, MaxTurnsExceeded)


def _tool_error_retry_prompt(original_prompt: dict[str, Any], exc: Exception) -> dict[str, Any]:
    return {
        "task": "Recover from an invalid tool call and continue the same coding task.",
        "previous_error": str(exc),
        "tool_call_warning": (
            "The previous attempt emitted an invalid tool call. Tool names must match exactly; "
            "do not add leading/trailing spaces or invent aliases."
        ),
        "valid_tool_names": CODER_TOOL_NAMES,
        "original_task": original_prompt,
    }


def _finish_after_max_turns_prompt(
    original_prompt: dict[str, Any],
    exc: Exception,
) -> dict[str, Any]:
    return {
        "task": "Finalize the current iteration after hitting the turn budget.",
        "previous_error": str(exc),
        "instructions": (
            "You reached the per-iteration turn budget. Do not investigate new approaches, "
            "do not redesign large sections, and do not call tools for broad exploration. "
            "Make only the minimum edits needed to leave index.html and related files renderable, "
            "save files immediately, then stop."
        ),
        "output_contract": "When files are saved, return exactly UPDATED_SOURCE_READY.",
        "original_task": original_prompt,
    }


def _source_manifest(source_root: Path) -> list[dict[str, Any]]:
    if not source_root.exists():
        return []
    return [
        {
            "path": str(path.relative_to(source_root)).replace("\\", "/"),
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(source_root.rglob("*"))
        if path.is_file()
    ]


def _clean_user_note(user_note: str | None) -> str | None:
    if user_note is None:
        return None
    stripped = user_note.strip()
    return stripped or None


def _one_line_preview(text: str, limit: int = 500) -> str:
    preview = " ".join((text or "").split())
    if len(preview) <= limit:
        return preview
    return f"{preview[:limit]}..."


def _log_info(message: str, *args: Any) -> None:
    job_logger = current_job_logger()
    if job_logger is not None:
        job_logger.info(message, *args)
    else:
        logger.info(message, *args)
