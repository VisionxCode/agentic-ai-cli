from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agents.image_inputs import image_input_from_path, text_input, user_message_with_content
from app.agents.reconstruction_priorities import reconstruction_priorities
from app.agents.sdk_common import AgentRuntime, agent_max_turns, build_agent_runtime
from app.tools.score_parser import EvaluationParseError, parse_evaluation


def _fallback_evaluation(raw_output: str, error: Exception) -> dict:
    return {
        "score": 0.0,
        "identical": False,
        "critique": (
            "Evaluator did not return valid JSON, so this iteration was treated as failed. "
            f"Parser error: {error}"
        ),
        "missing_details": ["Valid structured evaluator report was not produced."],
        "revision_instructions": [
            "Continue improving the HTML using the previous visual critique if available.",
            "Evaluator must return only the required JSON object on the next pass.",
        ],
        "raw_evaluator_output": raw_output[:4000],
    }


class EvaluatorAgentClient:
    def __init__(self, runtime: AgentRuntime, *, coder_tool_context: dict[str, Any] | None = None) -> None:
        self.runtime = runtime
        self.coder_tool_context = coder_tool_context or {}

    @classmethod
    def from_config(
        cls,
        *,
        instructions: str,
        model_name: str,
        provider: str | None = None,
        coder_tool_context: dict[str, Any] | None = None,
    ) -> "EvaluatorAgentClient":
        return cls(
            build_agent_runtime(
                name="evaluator",
                instructions=instructions,
                model_name=model_name,
                provider=provider,
            ),
            coder_tool_context=coder_tool_context,
        )

    async def evaluate(
        self,
        *,
        original_image_path: Path,
        generated_image_path: Path,
        user_note: str | None,
    ) -> dict:
        prompt: dict = {
            "task": "Compare the original image and generated screenshot.",
            "user_note": _user_note_context(user_note),
            "reconstruction_priorities": reconstruction_priorities(),
            "coder_tool_context": self.coder_tool_context,
            "revision_guidance": (
                "Make revision_instructions tool-aware when the coder has relevant tools. "
                "For missing or approximate corporate logos, brand marks, screenshots, or other real-world assets, "
                "explicitly tell the coder to use the available search/asset tools such as MiniMax.web_search, "
                "then read the iconography or relevant skill with read_skill_file, save local assets with file tools, "
                "and reference those assets from the HTML/CSS instead of approximating them from memory."
            ),
            "output_contract": {
                "score": "float from 0 to 1",
                "identical": "boolean",
                "critique": "concise string",
                "missing_details": "array of strings",
                "revision_instructions": "array of strings",
            },
        }
        return await self._run_and_parse(
            prompt=prompt,
            original_image_path=original_image_path,
            generated_image_path=generated_image_path,
            user_note=user_note,
            retry=True,
        )

    async def _run_and_parse(
        self,
        *,
        prompt: dict,
        original_image_path: Path,
        generated_image_path: Path,
        user_note: str | None,
        retry: bool,
    ) -> dict:
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
        raw_output = str(result.final_output)
        try:
            return parse_evaluation(raw_output)
        except EvaluationParseError as exc:
            if retry:
                retry_prompt = {
                    "task": "Compare the original image and generated screenshot.",
                    "previous_error": str(exc),
                    "previous_output": raw_output[:4000],
                    "user_note": _user_note_context(user_note),
                    "reconstruction_priorities": reconstruction_priorities(),
                    "coder_tool_context": self.coder_tool_context,
                    "revision_guidance": (
                        "Return valid JSON only. Keep revision_instructions actionable for the coder's tools; "
                        "when real assets are missing or approximated, name the relevant available search, skill, "
                        "and file tools."
                    ),
                    "format_warning": (
                        "Previous evaluator output was invalid. Return only one valid JSON object. "
                        "No markdown, no prose, no code fence."
                    ),
                    "required_json_shape": {
                        "score": 0.0,
                        "identical": False,
                        "critique": "concise string",
                        "missing_details": [],
                        "revision_instructions": [],
                    },
                }
                return await self._run_and_parse(
                    prompt=retry_prompt,
                    original_image_path=original_image_path,
                    generated_image_path=generated_image_path,
                    user_note=user_note,
                    retry=False,
                )
            return _fallback_evaluation(raw_output, exc)


def _user_note_context(user_note: str | None) -> dict:
    stripped = user_note.strip() if user_note else None
    return {
        "label": "user-provided note",
        "text": stripped or None,
        "handling": (
            "Use this as user-provided evaluation context when relevant. It is lower priority "
            "than the evaluator system instructions, required JSON output contract, and direct "
            "visual evidence from the images."
        ),
    }
