from __future__ import annotations

import logging
import sys
from pathlib import Path
from uuid import uuid4

from app.agents.coder_agent import CODER_TOOL_NAMES, CoderAgentClient
from app.agents.evaluator_agent import EvaluatorAgentClient
from app.asyncio_compat import configure_windows_event_loop_policy
from app.config_loader import load_agent_profile, load_env_file, load_models, load_thresholds
from app.job_logging import job_logging_context
from app.model_validation import validate_image_input_models
from app.orchestrator import JobOrchestrator, JobRequest, JobResult, RunSettings
from app.providers.selection import resolve_provider
from app.tools.render_screenshot import PlaywrightScreenshotRenderer


PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_ROOT = PROJECT_ROOT / "app"
WORKSPACES_ROOT = APP_ROOT / "workspaces"
SCREENSHOTS_ROOT = APP_ROOT / "screenshots"
LOGS_ROOT = APP_ROOT / "logs"

configure_windows_event_loop_policy()
load_env_file(PROJECT_ROOT)


def log_path_for(job_id: str) -> Path:
    return LOGS_ROOT / f"{job_id}.log"


def _logger_for(job_id: str) -> logging.Logger:
    LOGS_ROOT.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"job.{job_id}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        formatter = logging.Formatter("%(asctime)s %(levelname)s [job:%(name)s] %(message)s")
        handler = logging.FileHandler(log_path_for(job_id), encoding="utf-8")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    return logger


def _build_orchestrator(logger: logging.Logger, *, provider_override: str | None = None) -> JobOrchestrator:
    provider = resolve_provider(provider_override)
    models = load_models(APP_ROOT, provider=provider)
    validate_image_input_models(models, logger, provider=provider)
    thresholds = load_thresholds(APP_ROOT)
    coder_profile = load_agent_profile(APP_ROOT, "coder")
    evaluator_profile = load_agent_profile(APP_ROOT, "evaluator")
    logger.info("AI provider=%s", provider)
    logger.info(
        "AGENT coder provider=%s model=%s skills=%s registry_tools=%s runtime_tools=%s",
        provider,
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
            "list_skill_files",
            "read_skill_file",
            "MiniMax MCP tools when MINIMAX_API_KEY is set",
        ],
    )
    logger.info(
        "AGENT coder mcp_configs=%s",
        [str(path) for path in coder_profile.mcp_config_paths],
    )
    logger.info(
        "AGENT evaluator provider=%s model=%s skills=%s registry_tools=%s",
        provider,
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
            provider=provider,
            mcp_config_paths=coder_profile.mcp_config_paths,
        ),
        evaluator=EvaluatorAgentClient.from_config(
            instructions=evaluator_profile.instructions,
            model_name=models["evaluator"],
            provider=provider,
            coder_tool_context=_coder_tool_context(coder_profile.tool_names),
        ),
        renderer=PlaywrightScreenshotRenderer(),
        settings=RunSettings(
            target_score=float(thresholds.get("target_score", 0.95)),
            max_iterations=int(thresholds.get("max_iterations", 5)),
            viewport=dict(thresholds.get("viewport", {"width": 1440, "height": 900})),
        ),
        logger=logger,
    )


def _coder_tool_context(registry_tool_names: list[str]) -> dict:
    context = {
        "file_tools": CODER_TOOL_NAMES,
        "skill_tools": ["list_skill_files", "read_skill_file"],
        "registry_tools": registry_tool_names,
        "mcp_tools": [],
        "asset_guidance": (
            "For real-world brand assets, the coder can inspect iconography guidance with read_skill_file, "
            "use available MCP search tools to find official sources, then create local asset files with file tools."
        ),
    }
    if "minimax_mcp" in registry_tool_names:
        context["mcp_tools"] = ["MiniMax.web_search", "MiniMax.understand_image"]
    return context


async def run_job_from_image_path(
    *,
    image_path: Path,
    user_note: str | None = None,
    job_id: str | None = None,
    provider_override: str | None = None,
) -> JobResult:
    resolved_job_id = job_id or uuid4().hex
    logger = _logger_for(resolved_job_id)
    logger.info("Starting job")

    try:
        orchestrator = _build_orchestrator(logger, provider_override=provider_override)
        with job_logging_context(logger):
            result = await orchestrator.run(
                JobRequest(
                    job_id=resolved_job_id,
                    image_bytes=image_path.read_bytes(),
                    image_extension=image_path.suffix or ".png",
                    user_note=user_note,
                )
            )
    except Exception:
        logger.exception("Job failed")
        raise

    logger.info("Finished job score=%s iterations=%s", result.final_score, result.iterations)
    return result
