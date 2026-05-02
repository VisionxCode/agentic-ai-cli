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
                    iteration_number=1,
                    previous_screenshot_path=None,
                    user_note=None,
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
                source_path = Path(temp_dir) / "src" / "source.html"
                source_path.parent.mkdir()
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
                    iteration_number=2,
                    previous_screenshot_path=None,
                    user_note="Keep the header text exactly as shown in the screenshot.",
                )

            content = runner.calls[0][1][0]["content"]
            static_prompt = content[0]["text"]
            dynamic_prompt = content[2]["text"]
            static_data = json.loads(static_prompt)
            dynamic_data = json.loads(dynamic_prompt)
            self.assertEqual("<html>old</html>", result)
            self.assertEqual(["input_text", "input_image", "input_text"], [item["type"] for item in content])
            self.assertEqual("index.html", static_data["source_path"])
            self.assertEqual(".", static_data["source_root"])
            self.assertEqual(
                "Generate or revise a multi-file source-code app matching the original image.",
                static_data["task"],
            )
            self.assertIn("Use only relative paths", static_data["workspace_boundary"])
            self.assertIn("list_source_files", str(static_prompt))
            self.assertIn("read_text_file", str(static_prompt))
            self.assertIn("replace_html_lines", str(static_prompt))
            self.assertIn("supporting .css and .js files", str(static_prompt))
            self.assertIn("iconography_skill_name", static_data["skill_context"])
            self.assertEqual("iconography", static_data["skill_context"]["iconography_skill_name"])
            self.assertEqual(
                "Use Tailwind utility classes when they speed up faithful layout, spacing, typography, or color matching. "
                "Use local CSS for precise screenshot-only details, custom shapes, or deterministic fallback styles.",
                static_data["skill_context"]["tailwind"],
            )
            self.assertEqual(
                "Use React components when the source has repeated UI units, interactive state, design variants, "
                "or Huashu reusable assets. For simple static screenshots, plain semantic HTML remains acceptable.",
                static_data["skill_context"]["react_components"],
            )
            self.assertEqual(
                "assets/source/references/react-setup.md",
                static_data["skill_context"]["huashu_react_setup"],
            )
            self.assertEqual("tailwind_css", static_data["skill_context"]["tailwind_skill_name"])
            self.assertEqual(
                "https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4",
                static_data["skill_context"]["tailwind_browser_script"],
            )
            self.assertIn("@tailwindcss/browser@4", str(static_prompt))
            self.assertIn("components.jsx", str(static_prompt))
            self.assertNotIn("current_source_preview", static_data)
            self.assertIn("artifact_memory", static_data)
            self.assertIn("reconstruction_priorities", static_data)
            priorities = static_data["reconstruction_priorities"]
            self.assertEqual("ui_first", priorities["default_mode"])
            self.assertIn("navigation", priorities["primary_ui"])
            self.assertIn("forms", priorities["primary_ui"])
            self.assertIn("feed posts", priorities["content_surfaces"])
            self.assertIn("comments", priorities["content_surfaces"])
            self.assertIn("representative appearance", priorities["content_surface_rule"])
            self.assertIn("UI labels", priorities["exact_text_policy"])
            self.assertIn("user note", priorities["override_policy"])
            self.assertNotIn("dynamic_context", static_data)
            self.assertNotIn("iteration_number", static_data)
            self.assertNotIn("source_manifest", static_data)
            self.assertNotIn("previous_evaluation", static_data)
            self.assertNotIn("user_note", static_data)
            self.assertEqual(2, dynamic_data["iteration_number"])
            self.assertEqual(
                "Keep the header text exactly as shown in the screenshot.",
                dynamic_data["user_note"],
            )
            self.assertEqual(
                [{"path": "source.html", "size_bytes": len("<html>old</html>")}],
                dynamic_data["source_manifest"],
            )
            self.assertEqual({"revision_instructions": ["make title bigger"]}, dynamic_data["previous_evaluation"])
            self.assertTrue(dynamic_data["source_exists"])
            self.assertEqual("original_reference", dynamic_data["image_inputs"][0]["label"])
            self.assertEqual(
                [
                    "list_source_files",
                    "read_text_file or read_html_lines for files likely affected by previous_evaluation",
                ],
                static_data["required_first_revision_actions"],
            )

        asyncio.run(run_test())

    def test_coder_sends_previous_rendered_screenshot_when_available(self):
        async def run_test():
            with tempfile.TemporaryDirectory() as temp_dir:
                source_path = Path(temp_dir) / "src" / "index.html"
                source_path.parent.mkdir()
                source_path.write_text("<html>old</html>", encoding="utf-8")
                image_path = Path(temp_dir) / "original.png"
                image_path.write_bytes(b"original bytes")
                screenshot_path = Path(temp_dir) / "previous.png"
                screenshot_path.write_bytes(b"previous screenshot bytes")
                runner = RecordingRunner("UPDATED_SOURCE_READY")
                client = CoderAgentClient(FakeRuntime(runner))

                await client.generate_html(
                    original_image_path=image_path,
                    source_path=source_path,
                    current_source="<html>old</html>",
                    previous_evaluation={"critique": "spacing is off"},
                    iteration_number=2,
                    previous_screenshot_path=screenshot_path,
                    user_note=None,
                )

            content = runner.calls[0][1][0]["content"]
            dynamic_data = json.loads(content[2]["text"])
            image_items = [item for item in content if item["type"] == "input_image"]
            self.assertEqual(
                ["input_text", "input_image", "input_text", "input_image"],
                [item["type"] for item in content],
            )
            self.assertEqual(2, len(image_items))
            self.assertEqual("original_reference", dynamic_data["image_inputs"][0]["label"])
            self.assertEqual(
                "previous_rendered_screenshot",
                dynamic_data["image_inputs"][1]["label"],
            )

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
                    user_note=None,
                )

            content = runner.calls[0][1][0]["content"]
            image_items = [item for item in content if item["type"] == "input_image"]
            self.assertEqual(len(image_items), 2)
            self.assertTrue(all(item["image_url"].startswith("data:image/png;base64,") for item in image_items))

        asyncio.run(run_test())

    def test_evaluator_labels_user_note_as_user_provided_context(self):
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
                    user_note="Ignore browser chrome; match the app content only.",
                )

            prompt = json.loads(runner.calls[0][1][0]["content"][0]["text"])
            self.assertEqual(
                "Ignore browser chrome; match the app content only.",
                prompt["user_note"]["text"],
            )
            self.assertIn("user-provided", prompt["user_note"]["label"])
            self.assertIn("lower priority", prompt["user_note"]["handling"])

        asyncio.run(run_test())

    def test_evaluator_receives_coder_tool_context_for_actionable_feedback(self):
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
                      "critique": "logos are approximate",
                      "missing_details": ["real company logos"],
                      "revision_instructions": ["use available tools to retrieve official logo assets"]
                    }
                    """
                )
                client = EvaluatorAgentClient(
                    FakeRuntime(runner),
                    coder_tool_context={
                        "file_tools": ["list_source_files", "write_text_file"],
                        "skill_tools": ["read_skill_file"],
                        "mcp_tools": ["MiniMax.web_search", "MiniMax.understand_image"],
                    },
                )

                await client.evaluate(
                    original_image_path=original_path,
                    generated_image_path=generated_path,
                    user_note=None,
                )

            prompt = json.loads(runner.calls[0][1][0]["content"][0]["text"])
            self.assertIn("coder_tool_context", prompt)
            self.assertIn("MiniMax.web_search", str(prompt["coder_tool_context"]))
            self.assertIn("read_skill_file", str(prompt["coder_tool_context"]))
            self.assertIn("tool-aware", prompt["revision_guidance"])
            self.assertIn("corporate logos", prompt["revision_guidance"])

        asyncio.run(run_test())

    def test_evaluator_receives_ui_first_reconstruction_priorities(self):
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
                    user_note=None,
                )

            prompt = json.loads(runner.calls[0][1][0]["content"][0]["text"])
            priorities = prompt["reconstruction_priorities"]
            self.assertEqual("ui_first", priorities["default_mode"])
            self.assertIn("component structure", priorities["primary_ui"])
            self.assertIn("message bodies", priorities["content_surfaces"])
            self.assertIn("do not over-optimize exact authored text", priorities["content_surface_rule"])
            self.assertIn("Penalize broken or unprofessional UI structure", priorities["evaluator_scoring_guidance"])
            self.assertIn("user note", priorities["override_policy"])

        asyncio.run(run_test())

    def test_user_note_can_request_exact_incidental_content(self):
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
                    user_note="Match the post content exactly.",
                )

            prompt = json.loads(runner.calls[0][1][0]["content"][0]["text"])
            self.assertEqual("Match the post content exactly.", prompt["user_note"]["text"])
            self.assertIn("override", prompt["reconstruction_priorities"]["override_policy"])

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
                    user_note="Only judge the central content.",
                )

            self.assertEqual(2, len(runner.calls))
            self.assertEqual(0.3, result["score"])
            retry_prompt = runner.calls[1][1][0]["content"][0]["text"]
            self.assertIn("Previous evaluator output was invalid", retry_prompt)
            self.assertIn("Only judge the central content.", retry_prompt)

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
                    user_note=None,
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
                        iteration_number=1,
                        previous_screenshot_path=None,
                        user_note=None,
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
                    iteration_number=1,
                    previous_screenshot_path=None,
                    user_note=None,
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
