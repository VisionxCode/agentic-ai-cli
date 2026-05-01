import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.agents.coder_agent import CoderAgentClient
from app.agents.evaluator_agent import EvaluatorAgentClient
from app.agents.image_inputs import image_input_from_path
from app.agents.sdk_common import openrouter_setting


class FakeRunResult:
    def __init__(self, final_output):
        self.final_output = final_output


class RecordingRunner:
    def __init__(self, output):
        self.outputs = output if isinstance(output, list) else [output]
        self.calls = []

    async def run(self, agent, input_items, **kwargs):
        self.calls.append((agent, input_items, kwargs))
        index = min(len(self.calls) - 1, len(self.outputs) - 1)
        return FakeRunResult(self.outputs[index])


class ModelBehaviorRetryRunner:
    def __init__(self, retry_output):
        from agents.exceptions import ModelBehaviorError

        self.calls = []
        self.retry_output = retry_output
        self.error = ModelBehaviorError("Tool  read_html_file not found in agent coder")

    async def run(self, agent, input_items, **kwargs):
        self.calls.append((agent, input_items, kwargs))
        if len(self.calls) == 1:
            raise self.error
        return FakeRunResult(self.retry_output)


class FakeRuntime:
    def __init__(self, runner):
        self.agent = object()
        self.runner = runner


class AgentImageInputTests(unittest.TestCase):
    def test_openrouter_setting_strips_surrounding_whitespace(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "  secret-key\n"}, clear=True):
            self.assertEqual("secret-key", openrouter_setting("OPENROUTER_API_KEY"))

    def test_image_input_from_path_builds_data_url_image_payload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "original.png"
            image_path.write_bytes(b"png bytes")

            payload = image_input_from_path(image_path, detail="high")

        self.assertEqual(payload["type"], "input_image")
        self.assertEqual(payload["detail"], "high")
        self.assertTrue(payload["image_url"].startswith("data:image/png;base64,"))

    def test_coder_sends_original_image_as_sdk_image_input(self):
        async def run_test():
            with tempfile.TemporaryDirectory() as temp_dir:
                image_path = Path(temp_dir) / "original.png"
                image_path.write_bytes(b"png bytes")
                runner = RecordingRunner("<html></html>")
                client = CoderAgentClient(FakeRuntime(runner))

                await client.generate_html(
                    original_image_path=image_path,
                    source_path=Path(temp_dir) / "source.html",
                    current_source=None,
                    previous_evaluation=None,
                )

            input_items = runner.calls[0][1]
            content = input_items[0]["content"]
            self.assertEqual(input_items[0]["role"], "user")
            self.assertEqual(content[0]["type"], "input_text")
            self.assertEqual(content[1]["type"], "input_image")
            self.assertTrue(content[1]["image_url"].startswith("data:image/png;base64,"))

        asyncio.run(run_test())

    def test_coder_prompts_for_editing_existing_source_file(self):
        async def run_test():
            with tempfile.TemporaryDirectory() as temp_dir:
                source_path = Path(temp_dir) / "source.html"
                source_path.write_text("<html>old</html>", encoding="utf-8")
                image_path = Path(temp_dir) / "original.png"
                image_path.write_bytes(b"png bytes")
                runner = RecordingRunner("UPDATED_SOURCE_READY")
                client = CoderAgentClient(FakeRuntime(runner))

                result = await client.generate_html(
                    original_image_path=image_path,
                    source_path=source_path,
                    current_source="<html>old</html>",
                    previous_evaluation={"revision_instructions": ["make title bigger"]},
                )

            prompt = runner.calls[0][1][0]["content"][0]["text"]
            prompt_data = json.loads(prompt)
            self.assertEqual("<html>old</html>", result)
            self.assertEqual("index.html", prompt_data["source_path"])
            self.assertEqual(".", prompt_data["source_root"])
            self.assertIn("Use only relative paths", prompt_data["workspace_boundary"])
            self.assertIn("list_source_files", str(prompt))
            self.assertIn("read_text_file", str(prompt))
            self.assertIn("replace_html_lines", str(prompt))
            self.assertIn("supporting .css and .js files", str(prompt))

        asyncio.run(run_test())

    def test_evaluator_sends_both_images_as_sdk_image_inputs(self):
        async def run_test():
            with tempfile.TemporaryDirectory() as temp_dir:
                original_path = Path(temp_dir) / "original.png"
                generated_path = Path(temp_dir) / "generated.png"
                original_path.write_bytes(b"original")
                generated_path.write_bytes(b"generated")
                runner = RecordingRunner(
                    """
                    {
                      "score": 0.8,
                      "identical": false,
                      "critique": "close",
                      "missing_details": [],
                      "revision_instructions": []
                    }
                    """
                )
                client = EvaluatorAgentClient(FakeRuntime(runner))

                await client.evaluate(
                    original_image_path=original_path,
                    generated_image_path=generated_path,
                )

            content = runner.calls[0][1][0]["content"]
            image_items = [item for item in content if item["type"] == "input_image"]
            self.assertEqual(len(image_items), 2)
            self.assertTrue(all(item["image_url"].startswith("data:image/png;base64,") for item in image_items))

        asyncio.run(run_test())

    def test_evaluator_retries_once_when_output_is_not_json(self):
        async def run_test():
            with tempfile.TemporaryDirectory() as temp_dir:
                original_path = Path(temp_dir) / "original.png"
                generated_path = Path(temp_dir) / "generated.png"
                original_path.write_bytes(b"original")
                generated_path.write_bytes(b"generated")
                runner = RecordingRunner(
                    [
                        "The images are quite different.",
                        """
                        {
                          "score": 0.3,
                          "identical": false,
                          "critique": "different",
                          "missing_details": ["layout"],
                          "revision_instructions": ["rebuild layout"]
                        }
                        """,
                    ]
                )
                client = EvaluatorAgentClient(FakeRuntime(runner))

                result = await client.evaluate(
                    original_image_path=original_path,
                    generated_image_path=generated_path,
                )

            self.assertEqual(2, len(runner.calls))
            self.assertEqual(0.3, result["score"])
            retry_prompt = runner.calls[1][1][0]["content"][0]["text"]
            self.assertIn("Previous evaluator output was invalid", retry_prompt)

        asyncio.run(run_test())

    def test_evaluator_returns_fallback_report_when_retry_is_still_not_json(self):
        async def run_test():
            with tempfile.TemporaryDirectory() as temp_dir:
                original_path = Path(temp_dir) / "original.png"
                generated_path = Path(temp_dir) / "generated.png"
                original_path.write_bytes(b"original")
                generated_path.write_bytes(b"generated")
                runner = RecordingRunner(["not json", "still not json"])
                client = EvaluatorAgentClient(FakeRuntime(runner))

                result = await client.evaluate(
                    original_image_path=original_path,
                    generated_image_path=generated_path,
                )

            self.assertEqual(2, len(runner.calls))
            self.assertEqual(0.0, result["score"])
            self.assertFalse(result["identical"])
            self.assertIn("valid JSON", result["critique"])
            self.assertTrue(result["revision_instructions"])

        asyncio.run(run_test())

    def test_coder_uses_configurable_agent_max_turns(self):
        async def run_test():
            with tempfile.TemporaryDirectory() as temp_dir:
                image_path = Path(temp_dir) / "original.png"
                image_path.write_bytes(b"png bytes")
                source_path = Path(temp_dir) / "source.html"
                runner = RecordingRunner("<html></html>")
                client = CoderAgentClient(FakeRuntime(runner))

                with patch.dict(os.environ, {"OPENROUTER_AGENT_MAX_TURNS": "42"}):
                    await client.generate_html(
                        original_image_path=image_path,
                        source_path=source_path,
                        current_source=None,
                        previous_evaluation=None,
                    )

            self.assertEqual(42, runner.calls[0][2]["max_turns"])

        asyncio.run(run_test())

    def test_coder_retries_once_after_model_behavior_tool_error(self):
        async def run_test():
            with tempfile.TemporaryDirectory() as temp_dir:
                image_path = Path(temp_dir) / "original.png"
                image_path.write_bytes(b"png bytes")
                source_path = Path(temp_dir) / "src" / "index.html"
                runner = ModelBehaviorRetryRunner("<html>retry ok</html>")
                client = CoderAgentClient(FakeRuntime(runner))

                result = await client.generate_html(
                    original_image_path=image_path,
                    source_path=source_path,
                    current_source=None,
                    previous_evaluation=None,
                )

            self.assertEqual("<html>retry ok</html>", result)
            self.assertEqual(2, len(runner.calls))
            retry_prompt = json.loads(runner.calls[1][1][0]["content"][0]["text"])
            self.assertEqual("Recover from an invalid tool call and continue the same coding task.", retry_prompt["task"])
            self.assertIn("Tool  read_html_file not found", retry_prompt["previous_error"])
            self.assertIn("read_html_file", retry_prompt["valid_tool_names"])
            self.assertIn("must match exactly", retry_prompt["tool_call_warning"])

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
