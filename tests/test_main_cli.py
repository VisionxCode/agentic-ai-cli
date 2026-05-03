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

            async def fake_run_job_from_image_path(
                *,
                image_path,
                user_note,
                job_id,
                provider_override,
                viewport,
                max_iterations,
                target_score,
            ):
                self.assertEqual(Path(temp_dir) / "original.png", image_path)
                self.assertEqual("Match the compact layout.", user_note)
                self.assertIsNone(job_id)
                self.assertIsNone(provider_override)
                self.assertIsNone(viewport)
                self.assertIsNone(max_iterations)
                self.assertIsNone(target_score)
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

            async def fake_run_job_from_image_path(
                *,
                image_path,
                user_note,
                job_id,
                provider_override,
                viewport,
                max_iterations,
                target_score,
            ):
                self.assertIsNone(viewport)
                self.assertIsNone(max_iterations)
                self.assertIsNone(target_score)
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

    def test_cli_passes_provider_override_to_job_runner(self):
        from app import main

        result = JobResult(
            job_id="job-provider",
            status="completed",
            final_score=1.0,
            iterations=1,
            final_source_path=Path("final/source.html"),
            final_generated_image_path=Path("final/generated_image.png"),
            final_report_path=Path("final/report.json"),
            report={},
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "original.png"
            image_path.write_bytes(b"image bytes")
            stdout = io.StringIO()

            async def fake_run_job_from_image_path(
                *,
                image_path,
                user_note,
                job_id,
                provider_override,
                viewport,
                max_iterations,
                target_score,
            ):
                self.assertEqual("codex", provider_override)
                self.assertIsNone(viewport)
                self.assertIsNone(max_iterations)
                self.assertIsNone(target_score)
                return result

            with patch("app.main.run_job_from_image_path", fake_run_job_from_image_path):
                with redirect_stdout(stdout):
                    exit_code = main.main(["--image", str(image_path), "--provider", "codex"])

        self.assertEqual(0, exit_code)


    def test_cli_passes_runtime_controls_to_job_runner(self):
        from app import main

        result = JobResult(
            job_id="job-controls",
            status="completed",
            final_score=0.95,
            iterations=3,
            final_source_path=Path("final/source.html"),
            final_generated_image_path=Path("final/generated_image.png"),
            final_report_path=Path("final/report.json"),
            report={},
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "original.png"
            image_path.write_bytes(b"image bytes")
            stdout = io.StringIO()

            async def fake_run_job_from_image_path(
                *,
                image_path,
                user_note,
                job_id,
                provider_override,
                viewport,
                max_iterations,
                target_score,
            ):
                self.assertEqual({"width": 1280, "height": 720}, viewport)
                self.assertEqual(3, max_iterations)
                self.assertEqual(0.9, target_score)
                return result

            with patch("app.main.run_job_from_image_path", fake_run_job_from_image_path):
                with redirect_stdout(stdout):
                    exit_code = main.main(
                        [
                            "--image",
                            str(image_path),
                            "--viewport-width",
                            "1280",
                            "--viewport-height",
                            "720",
                            "--max-iterations",
                            "3",
                            "--target-score",
                            "0.9",
                        ]
                    )

        self.assertEqual(0, exit_code)

    def test_provider_select_saves_codex_provider_and_model(self):
        from app import main

        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = io.StringIO()
            with patch.dict("os.environ", {"AGENTIC_AI_CLI_HOME": temp_dir}, clear=True):
                with redirect_stdout(stdout):
                    exit_code = main.main(
                        [
                            "provider",
                            "select",
                            "--provider",
                            "codex",
                            "--codex-auth",
                            "skip",
                            "--model",
                            "gpt-codex-test",
                        ]
                    )

                config_path = Path(temp_dir) / "config.json"
                payload = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(0, exit_code)
        self.assertEqual("codex", payload["provider"])
        self.assertEqual("gpt-codex-test", payload["models"]["codex"]["coder"])
        self.assertIn("Provider saved: codex", stdout.getvalue())

    def test_provider_status_prints_saved_provider(self):
        from app import main

        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = io.StringIO()
            with patch.dict("os.environ", {"AGENTIC_AI_CLI_HOME": temp_dir}, clear=True):
                main.main(
                    [
                        "provider",
                        "select",
                        "--provider",
                        "codex",
                        "--codex-auth",
                        "skip",
                        "--model",
                        "gpt-codex-test",
                    ]
                )
                with redirect_stdout(stdout):
                    exit_code = main.main(["provider", "status"])

        self.assertEqual(0, exit_code)
        self.assertIn("provider: codex", stdout.getvalue())
        self.assertIn("coder_model: gpt-codex-test", stdout.getvalue())

    def test_auth_codex_import_command_imports_cli_auth_file(self):
        from app import main

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            codex_home = root / "codex"
            app_home = root / "app"
            codex_home.mkdir()
            (codex_home / "auth.json").write_text(
                json.dumps(
                    {
                        "tokens": {
                            "access_token": "access",
                            "refresh_token": "refresh",
                        }
                    }
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()

            with patch.dict(
                "os.environ",
                {"AGENTIC_AI_CLI_HOME": str(app_home), "CODEX_HOME": str(codex_home)},
                clear=True,
            ):
                with redirect_stdout(stdout):
                    exit_code = main.main(["auth", "codex", "import"])
                auth_file_exists = (app_home / "auth.json").exists()

        self.assertEqual(0, exit_code)
        self.assertIn("Codex credentials imported", stdout.getvalue())
        self.assertTrue(auth_file_exists)


if __name__ == "__main__":
    unittest.main()
