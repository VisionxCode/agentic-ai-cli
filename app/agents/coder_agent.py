from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agents.html_file_tools import build_html_file_tools
from app.agents.image_inputs import image_input_from_path, text_input, user_message_with_content
from app.agents.sdk_common import AgentRuntime, agent_max_turns, build_openrouter_agent
from app.agents.skill_file_tools import build_skill_file_tools
from app.mcp_loader import load_mcp_stdio_servers


APP_ROOT = Path(__file__).resolve().parents[1]


class CoderAgentClient:
    def __init__(self, runtime: AgentRuntime) -> None:
        self.runtime = runtime

    @classmethod
    def from_config(
        cls,
        *,
        instructions: str,
        model_name: str,
        mcp_config_paths: list[Path] | None = None,
    ) -> "CoderAgentClient":
        tools = [
            *build_html_file_tools(),
            *build_skill_file_tools(APP_ROOT / "skills"),
        ]
        return cls(
            build_openrouter_agent(
                name="coder",
                instructions=instructions,
                model_name=model_name,
                tools=tools,
                mcp_servers=load_mcp_stdio_servers(mcp_config_paths or []),
            )
        )

    async def generate_html(
        self,
        *,
        original_image_path: Path,
        source_path: Path,
        current_source: str | None,
        previous_evaluation: dict[str, Any] | None,
    ) -> str:
        source_exists = source_path.exists()
        source_root = source_path.parent
        prompt = {
            "task": "Generate or revise a multi-file HTML/CSS/JavaScript app matching the original image.",
            "source_path": str(source_path),
            "source_root": str(source_root),
            "skill_context": {
                "available_tools": [
                    "list_skill_files(skill_name, relative_dir='.')",
                    "read_skill_file(skill_name, relative_path, max_chars=30000)",
                ],
                "huashu_skill_name": "huashu_design",
                "huashu_main_skill": "assets/source/SKILL.md",
                "huashu_references_dir": "assets/source/references",
                "huashu_assets_dir": "assets/source/assets",
                "web_search": (
                    "When MiniMax MCP tools are available, use them for current product facts, "
                    "official brand assets, logos, screenshots, release/spec checks, and source URLs."
                ),
            },
            "workflow": (
                "If this is the first iteration, create source_path as the entry HTML file and create "
                "any supporting CSS or JavaScript files in source_root, for example styles.css and app.js. "
                "Use relative links from index.html so Playwright can load the files from disk. "
                "On later iterations, use list_source_files plus read_text_file/read_html_lines to inspect "
                "the existing app, then make targeted edits with replace_html_lines, "
                "insert_html_after_line, or write_text_file as appropriate. Do not recreate all files from "
                "scratch unless the existing app is unusable."
            ),
            "revision_rules": [
                "Before editing, search for the affected section and read nearby numbered lines.",
                "Prefer small line-range replacements in index.html and focused CSS/JavaScript file updates.",
                "Preserve useful existing HTML/CSS/JavaScript structure.",
                "Use write_html_file only for the first HTML draft or if source_path is corrupt/unusable.",
                "Use write_text_file to create or update supporting .css and .js files in source_root.",
                "After edits are saved, return UPDATED_SOURCE_READY instead of the whole document.",
            ],
            "source_exists": source_exists,
            "current_source_preview": current_source[:4000] if current_source else None,
            "previous_evaluation": previous_evaluation,
            "output_contract": (
                "Persist the entry HTML in source_path and supporting assets in source_root. If you return "
                "complete HTML, it will be written to source_path as a fallback. Otherwise return "
                "UPDATED_SOURCE_READY."
            ),
        }
        input_items = user_message_with_content(
            [
                text_input(prompt),
                image_input_from_path(original_image_path, detail="high"),
            ]
        )
        connect_mcp_servers = getattr(self.runtime, "connect_mcp_servers", None)
        if connect_mcp_servers is not None:
            await connect_mcp_servers()
        try:
            result = await self.runtime.runner.run(
                self.runtime.agent,
                input_items,
                max_turns=agent_max_turns(),
            )
        finally:
            cleanup_mcp_servers = getattr(self.runtime, "cleanup_mcp_servers", None)
            if cleanup_mcp_servers is not None:
                await cleanup_mcp_servers()
        output = str(result.final_output).strip()
        if output.lower().startswith("<!doctype") or output.lower().startswith("<html"):
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_text(output, encoding="utf-8")
        if source_path.exists():
            return source_path.read_text(encoding="utf-8").strip()
        return output
