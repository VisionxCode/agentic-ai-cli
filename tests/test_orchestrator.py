import tempfile
import unittest
import logging
from pathlib import Path

from app.orchestrator import JobOrchestrator, JobRequest, RunSettings


class FakeCoder:
    def __init__(self, change_on_revision=True):
        self.calls = []
        self.change_on_revision = change_on_revision

    async def generate_html(
        self, *, original_image_path, source_path, current_source, previous_evaluation
    ):
        self.calls.append((original_image_path, source_path, current_source, previous_evaluation))
        if previous_evaluation:
            if self.change_on_revision:
                source_path.write_text("<html>improved</html>", encoding="utf-8")
                (source_path.parent / "app.js").write_text("document.body.dataset.ready = 'yes';", encoding="utf-8")
            return source_path.read_text(encoding="utf-8")
        source_path.write_text("<html>first</html>", encoding="utf-8")
        (source_path.parent / "styles.css").write_text("body { margin: 0; }", encoding="utf-8")
        return source_path.read_text(encoding="utf-8")


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


class ScoredEvaluator:
    def __init__(self, scores):
        self.scores = scores
        self.calls = 0

    async def evaluate(self, *, original_image_path, generated_image_path):
        score = self.scores[self.calls]
        self.calls += 1
        return {
            "score": score,
            "identical": False,
            "critique": f"score {score}",
            "missing_details": [],
            "revision_instructions": ["keep improving"],
        }


class VersionedCoder:
    def __init__(self):
        self.calls = 0

    async def generate_html(
        self, *, original_image_path, source_path, current_source, previous_evaluation
    ):
        self.calls += 1
        source_path.write_text(f"<html>version {self.calls}</html>", encoding="utf-8")
        (source_path.parent / "styles.css").write_text(
            f"body {{ --version: {self.calls}; }}",
            encoding="utf-8",
        )
        return source_path.read_text(encoding="utf-8")


class FakeRenderer:
    def __init__(self):
        self.sources = []
        self.output_paths = []

    async def render(self, *, source_path, output_path, viewport):
        self.sources.append(Path(source_path).read_text(encoding="utf-8"))
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
            self.assertIn("Iteration 1/3: asking coder agent to generate/edit HTML", output)
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
            self.assertEqual(
                root / "workspaces" / "job-abc" / "working" / "src" / "index.html",
                coder.calls[0][1],
            )
            self.assertEqual(coder.calls[0][1], coder.calls[1][1])
            self.assertIsNotNone(coder.calls[1][3])
            self.assertEqual(renderer.sources, ["<html>first</html>", "<html>improved</html>"])
            final_src = root / "workspaces" / "job-abc" / "final" / "src"
            self.assertEqual((final_src / "styles.css").read_text(encoding="utf-8"), "body { margin: 0; }")
            self.assertEqual(
                (final_src / "app.js").read_text(encoding="utf-8"),
                "document.body.dataset.ready = 'yes';",
            )
            self.assertEqual(
                renderer.output_paths,
                [
                    root / "screenshots" / "job-abc" / "iterations" / "001.png",
                    root / "screenshots" / "job-abc" / "iterations" / "002.png",
                ],
            )

    async def test_logs_warning_when_revision_does_not_change_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = logging.getLogger("test.no-change")
            logger.handlers.clear()
            logger.propagate = True
            orchestrator = JobOrchestrator(
                workspaces_root=Path(temp_dir),
                coder=FakeCoder(change_on_revision=False),
                evaluator=FakeEvaluator(),
                renderer=FakeRenderer(),
                settings=RunSettings(target_score=0.9, max_iterations=3),
                logger=logger,
            )

            with self.assertLogs("test.no-change", level="WARNING") as logs:
                await orchestrator.run(
                    JobRequest(job_id="job-abc", image_bytes=b"original", image_extension=".png")
                )

            self.assertIn("coder did not change working source", "\n".join(logs.output))

    async def test_final_artifacts_use_highest_scoring_iteration_not_latest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            orchestrator = JobOrchestrator(
                workspaces_root=root / "workspaces",
                screenshots_root=root / "screenshots",
                coder=VersionedCoder(),
                evaluator=ScoredEvaluator([0.82, 0.51, 0.74]),
                renderer=FakeRenderer(),
                settings=RunSettings(target_score=0.95, max_iterations=3),
            )

            result = await orchestrator.run(
                JobRequest(job_id="job-best", image_bytes=b"original", image_extension=".png")
            )

            workspace = root / "workspaces" / "job-best"
            self.assertEqual("max_iterations_reached", result.status)
            self.assertEqual(0.82, result.final_score)
            self.assertEqual("<html>version 1</html>", result.final_source_path.read_text(encoding="utf-8"))
            self.assertEqual(
                "body { --version: 1; }",
                (workspace / "final" / "src" / "styles.css").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                "<html>version 1</html>",
                (workspace / "iterations" / "001" / "src" / "index.html").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                "<html>version 2</html>",
                (workspace / "iterations" / "002" / "src" / "index.html").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                "<html>version 3</html>",
                (workspace / "iterations" / "003" / "src" / "index.html").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
