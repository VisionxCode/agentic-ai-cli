from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agents.image_inputs import image_input_from_path, text_input, user_message_with_content
from app.agents.sdk_common import AgentRuntime, build_openrouter_agent


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
            )
        )

    async def generate_html(
        self,
        *,
        original_image_path: Path,
        current_source: str | None,
        previous_evaluation: dict[str, Any] | None,
    ) -> str:
        prompt = {
            "task": "Generate or revise a single self-contained HTML document matching the original image.",
            "current_source": current_source,
            "previous_evaluation": previous_evaluation,
            "output_contract": "Return only the complete HTML source. Do not wrap it in markdown.",
        }
        input_items = user_message_with_content(
            [
                text_input(prompt),
                image_input_from_path(original_image_path, detail="high"),
            ]
        )
        result = await self.runtime.runner.run(self.runtime.agent, input_items)
        return str(result.final_output).strip()
