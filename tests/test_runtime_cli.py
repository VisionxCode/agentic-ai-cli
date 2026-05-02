import io
import logging
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from app.orchestrator import JobResult


class RecordingOrchestrator:
    def __init__(self):
        self.requests = []

    async def run(self, request):
        self.requests.append(request)
        return JobResult(
            job_id=request.job_id,
            status="completed",
            final_score=1.0,
            iterations=1,
            final_source_path=Path("final/source.html"),
            final_generated_image_path=Path("final/generated_image.png"),
            final_report_path=Path("final/report.json"),
            report={"score": 1.0},
        )


class RuntimeCliTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_job_from_image_path_reads_image_and_preserves_request_fields(self):
        from app import runtime

        orchestrator = RecordingOrchestrator()

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "Original.PNG"
            image_path.write_bytes(b"image bytes")

            with patch("app.runtime._build_orchestrator", return_value=orchestrator):
                result = await runtime.run_job_from_image_path(
                    image_path=image_path,
                    user_note="Match the compact mobile layout.",
                    job_id="fixed-job",
                )

        self.assertEqual("fixed-job", result.job_id)
        self.assertEqual(1, len(orchestrator.requests))
        request = orchestrator.requests[0]
        self.assertEqual("fixed-job", request.job_id)
        self.assertEqual(b"image bytes", request.image_bytes)
        self.assertEqual(".PNG", request.image_extension)
        self.assertEqual("Match the compact mobile layout.", request.user_note)

    async def test_job_logger_writes_console_logs_to_stderr(self):
        from app import runtime

        logging.getLogger("job.stderr-job").handlers.clear()
        stdout = io.StringIO()
        stderr = io.StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            logger = runtime._logger_for("stderr-job")
            logger.info("hello from logger")

        self.assertEqual("", stdout.getvalue())
        self.assertIn("hello from logger", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
