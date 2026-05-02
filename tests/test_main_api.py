import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app, jobs
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
            final_source_path=Path("final/src/index.html"),
            final_generated_image_path=Path("final/generated_image.png"),
            final_report_path=Path("final/report.json"),
            report={"score": 1.0},
        )


class MainApiTests(unittest.TestCase):
    def tearDown(self):
        jobs.clear()

    def test_create_job_accepts_optional_user_note_form_field(self):
        orchestrator = RecordingOrchestrator()

        with patch("app.main._build_orchestrator", return_value=orchestrator):
            response = TestClient(app).post(
                "/jobs",
                files={"original_image": ("original.png", b"image bytes", "image/png")},
                data={"user_note": "Match the compact mobile layout."},
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("Match the compact mobile layout.", orchestrator.requests[0].user_note)


if __name__ == "__main__":
    unittest.main()
