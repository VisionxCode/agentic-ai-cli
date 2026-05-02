import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from app.orchestrator import JobResult


class MainCliTests(unittest.TestCase):
    def test_cli_prints_text_summary_for_completed_job(self):
        from app import main

        result = JobResult(
            job_id="job-123",
            status="completed",
            final_score=0.98,
            iterations=2,
            final_source_path=Path("final/source.html"),
            final_generated_image_path=Path("final/generated_image.png"),
            final_report_path=Path("final/report.json"),
            report={"score": 0.98},
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "original.png"
            image_path.write_bytes(b"image bytes")
            stdout = io.StringIO()

            async def fake_run_job_from_image_path(*, image_path, user_note, job_id):
                self.assertEqual(Path(temp_dir) / "original.png", image_path)
                self.assertEqual("Match the compact layout.", user_note)
                self.assertIsNone(job_id)
                return result

            with patch("app.main.run_job_from_image_path", fake_run_job_from_image_path):
                with redirect_stdout(stdout):
                    exit_code = main.main(
                        ["--image", str(image_path), "--note", "Match the compact layout."]
                    )

        self.assertEqual(0, exit_code)
        output = stdout.getvalue()
        self.assertIn("job_id: job-123", output)
        self.assertIn("status: completed", output)
        self.assertIn("final_score: 0.98", output)
        self.assertIn("iterations: 2", output)
        self.assertIn("final_source_path: final/source.html", output)
        self.assertIn("final_generated_image_path: final/generated_image.png", output)
        self.assertIn("final_report_path: final/report.json", output)
        self.assertIn("log_path:", output)

    def test_cli_prints_json_when_requested(self):
        from app import main

        result = JobResult(
            job_id="job-json",
            status="completed",
            final_score=1.0,
            iterations=1,
            final_source_path=Path("final/source.html"),
            final_generated_image_path=Path("final/generated_image.png"),
            final_report_path=Path("final/report.json"),
            report={"score": 1.0},
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "original.jpg"
            image_path.write_bytes(b"image bytes")
            stdout = io.StringIO()

            async def fake_run_job_from_image_path(*, image_path, user_note, job_id):
                return result

            with patch("app.main.run_job_from_image_path", fake_run_job_from_image_path):
                with redirect_stdout(stdout):
                    exit_code = main.main(["--image", str(image_path), "--json"])

        self.assertEqual(0, exit_code)
        payload = json.loads(stdout.getvalue())
        self.assertEqual("job-json", payload["job_id"])
        self.assertEqual("completed", payload["status"])
        self.assertEqual("final/source.html", payload["final_source_path"])
        self.assertIn("log_path", payload)

    def test_cli_returns_nonzero_for_missing_image_path(self):
        from app import main

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = main.main(["--image", "missing.png"])

        self.assertEqual(2, exit_code)
        self.assertIn("Image path does not exist", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
