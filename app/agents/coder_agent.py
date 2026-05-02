from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agents.html_file_tools import build_html_file_tools
from app.agents.image_inputs import image_input_from_path, text_input, user_message_with_content
from app.agents.sdk_common import AgentRuntime, agent_max_turns, build_openrouter_agent
from app.agents.skill_file_tools import build_skill_file_tools
from app.mcp_loader import load_mcp_stdio_servers


APP_ROOT = Path(__file__).resolve().parents[1]

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
        mcp_config_paths: list[Path] | None = None,
    ) -> None:
        self.runtime = runtime
        self.instructions = instructions
        self.model_name = model_name
        self.mcp_config_paths = mcp_config_paths or []

    @classmethod
    def from_config(
        cls,
        *,
        instructions: str,
        model_name: str,
        mcp_config_paths: list[Path] | None = None,
    ) -> "CoderAgentClient":
        return cls(
            instructions=instructions,
            model_name=model_name,
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
        image_inputs = [{"label": "original_reference", "detail": "high"}]
        if previous_screenshot_path is not None:
            image_inputs.append({"label": "previous_rendered_screenshot", "detail": "high"})
        static_prompt = {
            "task": "Generate or revise a multi-file source-code app matching the original image.",
            "source_path": "index.html",
            "source_root": ".",
            "workspace_boundary": (
                "The file tools are scoped to this job's source folder. Use only relative paths "
                "such as index.html, styles.css, and app.js. Do not use absolute paths."
            ),
            "skill_context": {
                "available_tools": [
                    "list_skill_files(skill_name, relative_dir='.')",
                    "read_skill_file(skill_name, relative_path, max_chars=30000)",
                ],
                "image_sourcecode_skill_name": "image_to_sourcecode",
                "iconography_skill_name": "iconography",
                "tailwind_skill_name": "tailwind_css",
                "tailwind_browser_script": "https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4",
                "huashu_skill_name": "huashu_design",
                "huashu_main_skill": "assets/source/SKILL.md",
                "huashu_references_dir": "assets/source/references",
                "huashu_react_setup": "assets/source/references/react-setup.md",
                "huashu_assets_dir": "assets/source/assets",
                "tailwind": (
                    "Use Tailwind utility classes when they speed up faithful layout, spacing, typography, or color matching. "
                    "Use local CSS for precise screenshot-only details, custom shapes, or deterministic fallback styles."
                ),
                "react_components": (
                    "Use React components when the source has repeated UI units, interactive state, design variants, "
                    "or Huashu reusable assets. For simple static screenshots, plain semantic HTML remains acceptable."
                ),
                "icons": (
                    "For icon or vector asset decisions, read the iconography skill. Prefer inline/local SVG "
                    "for deterministic screenshot matching. Use Google Material Symbols as the default "
                    "coherent UI icon vocabulary when font loading is acceptable, and Iconify/MCP retrieval "
                    "for broader or branded icon sets when available."
                ),
                "web_search": (
                    "When MiniMax MCP tools are available, use them for current product facts, "
                    "official brand assets, logos, screenshots, release/spec checks, and source URLs."
                ),
            },
            "workflow": (
                "If this is the first iteration, create source_path as the entry file for the current web target "
                "and create any supporting CSS, JavaScript, or local asset files in source_root, for example "
                "styles.css, app.js, components.jsx, and icons.svg. "
                "Use relative links from index.html so Playwright can load the files from disk. "
                "When Tailwind is helpful for fast faithful layout, include the Tailwind browser script "
                "from https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4 and still keep local CSS for exact visual details or fallback styling. "
                "When React components are helpful, use the Huashu React+Babel pattern: pinned React and Babel scripts, "
                "script type=\"text/babel\" component files such as components.jsx, unique per-file style object names, "
                "and Object.assign(window, {...}) for any cross-file components. "
                "On later iterations, use list_source_files plus read_text_file/read_html_lines to inspect "
                "the existing app, then make targeted edits with replace_html_lines, "
                "insert_html_after_line, or write_text_file as appropriate. Do not recreate all files from "
                "scratch unless the existing app is unusable."
            ),
            "artifact_memory": {
                "principle": (
                    "Treat saved artifacts as the source of truth. Use the working source files, "
                    "previous rendered screenshot, and previous evaluator report to understand what "
                    "changed and what still needs correction."
                ),
                "source_files": "The full current app is on disk under source_root; inspect it with file tools instead of relying on prompt source text.",
                "render_feedback": "When provided, compare the previous rendered screenshot against the original reference image before editing.",
                "evaluation_feedback": "Use previous_evaluation as the latest critique and priority list for targeted fixes.",
            },
            "required_first_revision_actions": [
                "list_source_files",
                "read_text_file or read_html_lines for files likely affected by previous_evaluation",
            ],
            "revision_rules": [
                "Use tool names exactly as listed. Never add spaces, punctuation, namespace prefixes, or aliases.",
                "For revision iterations, first call list_source_files, then read_text_file or read_html_lines before editing.",
                "Before editing, search for the affected section and read nearby numbered lines.",
                "Prefer small line-range replacements in index.html and focused CSS/JavaScript file updates.",
                "Preserve useful existing HTML/CSS/JavaScript structure.",
                "Use write_html_file only for the first HTML draft or if source_path is corrupt/unusable.",
                "Use write_text_file to create or update supporting .css and .js files in source_root.",
                "After edits are saved, return UPDATED_SOURCE_READY instead of the whole document.",
            ],
            "output_contract": (
                "Persist the entry HTML in source_path and supporting assets in source_root. If you return "
                "complete HTML, it will be written to source_path as a fallback. Otherwise return "
                "UPDATED_SOURCE_READY."
            ),
        }
        dynamic_context = {
            "iteration_number": iteration_number,
            "source_exists": source_exists,
            "source_manifest": _source_manifest(source_root),
            "previous_evaluation": previous_evaluation,
            "user_note": _clean_user_note(user_note),
            "image_inputs": image_inputs,
        }
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
        if output.lower().startswith("<!doctype") or output.lower().startswith("<html"):
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_text(output, encoding="utf-8")
        if source_path.exists():
            return source_path.read_text(encoding="utf-8").strip()
        return output

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
            if not _is_model_behavior_error(exc):
                raise
            retry_prompt = _tool_error_retry_prompt(original_prompt, exc)
            return await runtime.runner.run(
                runtime.agent,
                user_message_with_content([text_input(retry_prompt)]),
                max_turns=agent_max_turns(),
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
        return build_openrouter_agent(
            name="coder",
            instructions=self.instructions,
            model_name=self.model_name,
            tools=tools,
            mcp_servers=load_mcp_stdio_servers(self.mcp_config_paths),
        )


def _is_model_behavior_error(exc: Exception) -> bool:
    try:
        from agents.exceptions import ModelBehaviorError
    except ModuleNotFoundError:
        return False
    return isinstance(exc, ModelBehaviorError)


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
