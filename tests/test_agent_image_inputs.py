import asyncio
import tempfile
import unittest
from pathlib import Path

from app.agents.coder_agent import CoderAgentClient
from app.agents.evaluator_agent import EvaluatorAgentClient
from app.agents.image_inputs import image_input_from_path


class FakeRunResult:
    def __init__(self, final_output):
        self.final_output = final_output


class RecordingRunner:
    def __init__(self, output):
        self.output = output
        self.calls = []

    async def run(self, agent, input_items):
        self.calls.append((agent, input_items))
        return FakeRunResult(self.output)


class FakeRuntime:
    def __init__(self, runner):
        self.agent = object()
        self.runner = runner


class AgentImageInputTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
