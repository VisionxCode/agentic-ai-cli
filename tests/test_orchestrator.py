import tempfile
import unittest
import logging
from pathlib import Path

from app.orchestrator import JobOrchestrator, JobRequest, RunSettings


class FakeCoder:
    def __init__(self):
        self.calls = []

    async def generate_html(self, *, original_image_path, current_source, previous_evaluation):
        self.calls.append((original_image_path, current_source, previous_evaluation))
        if previous_evaluation:
            return "<html>improved</html>"
        return "<html>first</html>"


class FakeEvaluator:
    def __init__(self):
        self.calls = 0

    async def evaluate(self, *, original_image_path, generated_image_path):
        self.calls += 1
        if self.calls == 1:
            return {
                "score": 0.4,
                "identical": False,
                "critique": "needs work",
                "missing_details": ["spacing"],
                "revision_instructions": ["improve spacing"],
            }
        return {
            "score": 0.93,
            "identical": True,
            "critique": "done",
            "missing_details": [],
            "revision_instructions": [],
        }


class FakeRenderer:
    def __init__(self):
        self.sources = []
        self.output_paths = []

    async def render(self, *, source_html, output_path, viewport):
        self.sources.append(source_html)
        self.output_paths.append(Path(output_path))
        Path(output_path).write_bytes(b"png")
        return Path(output_path)


class OrchestratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_logs_each_workflow_stage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = logging.getLogger("test.job-progress")
            logger.handlers.clear()
            logger.propagate = True
            orchestrator = JobOrchestrator(
                workspaces_root=Path(temp_dir),
                coder=FakeCoder(),
                evaluator=FakeEvaluator(),
                renderer=FakeRenderer(),
                settings=RunSettings(target_score=0.9, max_iterations=3),
                logger=logger,
            )

            with self.assertLogs("test.job-progress", level="INFO") as logs:
                await orchestrator.run(
                    JobRequest(job_id="job-abc", image_bytes=b"original", image_extension=".png")
                )

            output = "\n".join(logs.output)
            self.assertIn("Job job-abc initialized", output)
            self.assertIn("Iteration 1/3: asking coder agent to generate HTML", output)
            self.assertIn("Iteration 1/3: rendering HTML screenshot", output)
            self.assertIn("Iteration 1/3: asking evaluator agent to compare images", output)
            self.assertIn("Iteration 1/3: score=0.4", output)
            self.assertIn("Iteration 2/3: target reached", output)

    async def test_runs_iterations_until_threshold_and_saves_final_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coder = FakeCoder()
            evaluator = FakeEvaluator()
            renderer = FakeRenderer()
            orchestrator = JobOrchestrator(
                workspaces_root=root / "workspaces",
                screenshots_root=root / "screenshots",
                coder=coder,
                evaluator=evaluator,
                renderer=renderer,
                settings=RunSettings(target_score=0.9, max_iterations=3),
            )

            result = await orchestrator.run(
                JobRequest(job_id="job-abc", image_bytes=b"original", image_extension=".png")
            )

            self.assertEqual(result.status, "completed")
            self.assertEqual(result.final_score, 0.93)
            self.assertEqual(result.iterations, 2)
            self.assertTrue(result.final_source_path.exists())
            self.assertTrue(result.final_generated_image_path.exists())
            self.assertIsNotNone(coder.calls[1][2])
            self.assertEqual(renderer.sources, ["<html>first</html>", "<html>improved</html>"])
            self.assertEqual(
                renderer.output_paths,
                [
                    root / "screenshots" / "job-abc" / "iterations" / "001.png",
                    root / "screenshots" / "job-abc" / "iterations" / "002.png",
                ],
            )


if __name__ == "__main__":
    unittest.main()
