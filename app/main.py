from __future__ import annotations

import logging
import sys
from pathlib import Path
from uuid import uuid4

from app.asyncio_compat import configure_windows_event_loop_policy
from app.agents.coder_agent import CoderAgentClient
from app.agents.evaluator_agent import EvaluatorAgentClient
from app.config_loader import load_agent_profile, load_env_file, load_models, load_thresholds
from app.job_logging import job_logging_context
from app.model_validation import validate_image_input_models
from app.orchestrator import JobOrchestrator, JobRequest, RunSettings
from app.tools.render_screenshot import PlaywrightScreenshotRenderer

try:
    from fastapi import FastAPI, File, HTTPException, UploadFile
    from fastapi.responses import FileResponse
except ModuleNotFoundError as exc:
    raise RuntimeError("Install REST dependencies with 'uv sync' or 'pip install -e .'") from exc


PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKSPACES_ROOT = PROJECT_ROOT / "app" / "workspaces"
SCREENSHOTS_ROOT = PROJECT_ROOT / "app" / "screenshots"
LOGS_ROOT = PROJECT_ROOT / "app" / "logs"
configure_windows_event_loop_policy()
load_env_file(PROJECT_ROOT)

app = FastAPI(title="Image-to-HTML Agent Workflow")
jobs: dict[str, dict] = {}


def _logger_for(job_id: str) -> logging.Logger:
    LOGS_ROOT.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"job.{job_id}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        formatter = logging.Formatter("%(asctime)s %(levelname)s [job:%(name)s] %(message)s")
        handler = logging.FileHandler(LOGS_ROOT / f"{job_id}.log", encoding="utf-8")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    return logger


def _build_orchestrator(logger: logging.Logger) -> JobOrchestrator:
    models = load_models(PROJECT_ROOT / "app")
    validate_image_input_models(models, logger)
    thresholds = load_thresholds(PROJECT_ROOT / "app")
    coder_profile = load_agent_profile(PROJECT_ROOT / "app", "coder")
    evaluator_profile = load_agent_profile(PROJECT_ROOT / "app", "evaluator")
    logger.info(
        "AGENT coder model=%s skills=%s registry_tools=%s runtime_tools=%s",
        models["coder"],
        [str(path) for path in coder_profile.skill_paths],
        coder_profile.tool_names,
        [
            "read_html_file",
            "search_html_file",
            "read_html_lines",
            "replace_html_lines",
            "insert_html_after_line",
            "write_html_file",
            "list_source_files",
            "read_text_file",
            "write_text_file",
        ],
    )
    logger.info(
        "AGENT evaluator model=%s skills=%s registry_tools=%s",
        models["evaluator"],
        [str(path) for path in evaluator_profile.skill_paths],
        evaluator_profile.tool_names,
    )

    return JobOrchestrator(
        workspaces_root=WORKSPACES_ROOT,
        screenshots_root=SCREENSHOTS_ROOT,
        coder=CoderAgentClient.from_config(
            instructions=coder_profile.instructions,
            model_name=models["coder"],
        ),
        evaluator=EvaluatorAgentClient.from_config(
            instructions=evaluator_profile.instructions,
            model_name=models["evaluator"],
        ),
        renderer=PlaywrightScreenshotRenderer(),
        settings=RunSettings(
            target_score=float(thresholds.get("target_score", 0.95)),
            max_iterations=int(thresholds.get("max_iterations", 5)),
            viewport=dict(thresholds.get("viewport", {"width": 1440, "height": 900})),
        ),
        logger=logger,
    )


@app.post("/jobs")
async def create_job(original_image: UploadFile = File(...)) -> dict:
    suffix = Path(original_image.filename or "original_image.png").suffix or ".png"
    job_id = uuid4().hex
    jobs[job_id] = {"status": "running", "current_iteration": 0, "current_score": None}
    logger = _logger_for(job_id)
    logger.info("Starting job")

    try:
        orchestrator = _build_orchestrator(logger)
        with job_logging_context(logger):
            result = await orchestrator.run(
                JobRequest(
                    job_id=job_id,
                    image_bytes=await original_image.read(),
                    image_extension=suffix,
                )
            )
    except Exception as exc:
        logger.exception("Job failed")
        jobs[job_id] = {"status": "failed", "error": str(exc)}
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    jobs[job_id] = {
        "status": result.status,
        "current_iteration": result.iterations,
        "current_score": result.final_score,
        "final_source_path": str(result.final_source_path),
        "final_generated_image_path": str(result.final_generated_image_path),
        "final_report_path": str(result.final_report_path),
        "report": result.report,
    }
    logger.info("Finished job score=%s iterations=%s", result.final_score, result.iterations)
    return {"job_id": job_id, **jobs[job_id]}


@app.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return {"job_id": job_id, **jobs[job_id]}


@app.get("/jobs/{job_id}/result")
async def get_result(job_id: str) -> dict:
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    workspace = WORKSPACES_ROOT / job_id / "final"
    if not workspace.exists():
        raise HTTPException(status_code=404, detail="Result is not ready")
    return {
        "job_id": job_id,
        "source": str(workspace / "source.html"),
        "source_root": str(workspace / "src"),
        "entrypoint": str(workspace / "src" / "index.html"),
        "generated_image": str(workspace / "generated_image.png"),
        "report": str(workspace / "report.json"),
    }


@app.get("/jobs/{job_id}/iterations")
async def list_iterations(job_id: str) -> dict:
    root = WORKSPACES_ROOT / job_id / "iterations"
    if not root.exists():
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return {
        "job_id": job_id,
        "iterations": [
            {
                "iteration": item.name,
                "source": str(item / "source.html"),
                "source_root": str(item / "src"),
                "entrypoint": str(item / "src" / "index.html"),
                "generated_image": str(item / "generated_image.png"),
                "evaluation": str(item / "evaluation.json"),
            }
            for item in sorted(root.iterdir())
            if item.is_dir()
        ],
    }


@app.get("/jobs/{job_id}/iterations/{number}/{artifact}")
async def get_iteration_artifact(job_id: str, number: int, artifact: str) -> FileResponse:
    allowed = {
        "source": "source.html",
        "screenshot": "generated_image.png",
        "evaluation": "evaluation.json",
    }
    if artifact not in allowed:
        raise HTTPException(status_code=404, detail="Unknown artifact")
    path = WORKSPACES_ROOT / job_id / "iterations" / f"{number:03d}" / allowed[artifact]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(path)
