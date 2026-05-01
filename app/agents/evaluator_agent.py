from __future__ import annotations

from pathlib import Path

from app.agents.image_inputs import image_input_from_path, text_input, user_message_with_content
from app.agents.sdk_common import AgentRuntime, agent_max_turns, build_openrouter_agent
from app.tools.score_parser import parse_evaluation


class EvaluatorAgentClient:
    def __init__(self, runtime: AgentRuntime) -> None:
        self.runtime = runtime

    @classmethod
    def from_config(cls, *, instructions: str, model_name: str) -> "EvaluatorAgentClient":
        return cls(
            build_openrouter_agent(
                name="evaluator",
                instructions=instructions,
                model_name=model_name,
            )
        )

    async def evaluate(self, *, original_image_path: Path, generated_image_path: Path) -> dict:
        prompt = {
            "task": "Compare the original image and generated screenshot.",
            "output_contract": {
                "score": "float from 0 to 1",
                "identical": "boolean",
                "critique": "concise string",
                "missing_details": "array of strings",
                "revision_instructions": "array of strings",
            },
        }
        input_items = user_message_with_content(
            [
                text_input(prompt),
                image_input_from_path(original_image_path, detail="high"),
                image_input_from_path(generated_image_path, detail="high"),
            ]
        )
        result = await self.runtime.runner.run(
            self.runtime.agent,
            input_items,
            max_turns=agent_max_turns(),
        )
        return parse_evaluation(str(result.final_output))
