from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agents.html_file_tools import build_html_file_tools
from app.agents.image_inputs import image_input_from_path, text_input, user_message_with_content
from app.agents.sdk_common import AgentRuntime, agent_max_turns, build_openrouter_agent


class CoderAgentClient:
    def __init__(self, runtime: AgentRuntime) -> None:
        self.runtime = runtime

    @classmethod
    def from_config(cls, *, instructions: str, model_name: str) -> "CoderAgentClient":
        return cls(
            build_openrouter_agent(
                name="coder",
                instructions=instructions,
                model_name=model_name,
                tools=build_html_file_tools(),
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
        prompt = {
            "task": "Generate or revise a single self-contained HTML document matching the original image.",
            "source_path": str(source_path),
            "workflow": (
                "If this is the first iteration, create the complete HTML and write it to source_path. "
                "On later iterations, use the available file tools to read/search line ranges in "
                "source_path, then make targeted edits with replace_html_lines or insert_html_after_line. "
                "Do not recreate the document from scratch unless the existing file is unusable."
            ),
            "revision_rules": [
                "Before editing, search for the affected section and read nearby numbered lines.",
                "Prefer small line-range replacements over full-file writes.",
                "Preserve useful existing HTML/CSS structure.",
                "Use write_html_file only for the first draft or if source_path is corrupt/unusable.",
                "After edits are saved, return UPDATED_SOURCE_READY instead of the whole document.",
            ],
            "source_exists": source_exists,
            "current_source_preview": current_source[:4000] if current_source else None,
            "previous_evaluation": previous_evaluation,
            "output_contract": (
                "Persist the final HTML in source_path. If you return complete HTML, it will be written "
                "to source_path as a fallback. Otherwise return UPDATED_SOURCE_READY."
            ),
        }
        input_items = user_message_with_content(
            [
                text_input(prompt),
                image_input_from_path(original_image_path, detail="high"),
            ]
        )
        result = await self.runtime.runner.run(
            self.runtime.agent,
            input_items,
            max_turns=agent_max_turns(),
        )
        output = str(result.final_output).strip()
        if output.lower().startswith("<!doctype") or output.lower().startswith("<html"):
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_text(output, encoding="utf-8")
        if source_path.exists():
            return source_path.read_text(encoding="utf-8").strip()
        return output
