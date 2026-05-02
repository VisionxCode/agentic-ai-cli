from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.workspace import IterationArtifacts, JobWorkspace


DEFAULT_VIEWPORT = {"width": 1440, "height": 900}


class Coder(Protocol):
    async def generate_html(
        self,
        *,
        original_image_path: Path,
        source_path: Path,
        current_source: str | None,
        previous_evaluation: dict[str, Any] | None,
        iteration_number: int,
        previous_screenshot_path: Path | None,
        user_note: str | None,
    ) -> str: ...


class Evaluator(Protocol):
    async def evaluate(
        self, *, original_image_path: Path, generated_image_path: Path, user_note: str | None
    ) -> dict[str, Any]: ...


class Renderer(Protocol):
    async def render(self, *, source_path: Path, output_path: Path, viewport: dict[str, int]) -> Path: ...


@dataclass(frozen=True)
class RunSettings:
    target_score: float = 0.95
    max_iterations: int = 5
    viewport: dict[str, int] | None = None


@dataclass(frozen=True)
class JobRequest:
    job_id: str
    image_bytes: bytes
    image_extension: str = ".png"
    user_note: str | None = None


@dataclass(frozen=True)
class JobResult:
    job_id: str
    status: str
    final_score: float
    iterations: int
    final_source_path: Path
    final_generated_image_path: Path
    final_report_path: Path
    report: dict[str, Any]


@dataclass(frozen=True)
class BestIteration:
    artifacts: IterationArtifacts
    evaluation: dict[str, Any]
    score: float


class JobOrchestrator:
    def __init__(
        self,
        *,
        workspaces_root: Path,
        screenshots_root: Path | None = None,
        coder: Coder,
        evaluator: Evaluator,
        renderer: Renderer,
        settings: RunSettings,
        logger: logging.Logger | None = None,
    ) -> None:
        self.workspaces_root = workspaces_root
        self.screenshots_root = screenshots_root or workspaces_root.parent / "screenshots"
        self.coder = coder
        self.evaluator = evaluator
        self.renderer = renderer
        self.settings = settings
        self.logger = logger or logging.getLogger(__name__)

    async def run(self, request: JobRequest) -> JobResult:
        workspace = JobWorkspace.create(self.workspaces_root, request.job_id)
        original_path = workspace.save_original_image(request.image_bytes, request.image_extension)
        viewport = self.settings.viewport or DEFAULT_VIEWPORT
        self.logger.info(
            "Job %s initialized: original=%s viewport=%sx%s target_score=%s max_iterations=%s",
            request.job_id,
            original_path,
            viewport.get("width"),
            viewport.get("height"),
            self.settings.target_score,
            self.settings.max_iterations,
        )

        current_source: str | None = None
        previous_evaluation: dict[str, Any] | None = None
        last_screenshot: Path | None = None
        best: BestIteration | None = None
        source_root = workspace.root / "working" / "src"
        source_path = source_root / "index.html"
        source_path.parent.mkdir(parents=True, exist_ok=True)

        for iteration in range(1, self.settings.max_iterations + 1):
            if best is not None and not _best_is_previous_iteration(best, iteration):
                _restore_source_tree(source_root=source_root, iteration=best.artifacts)
                current_source = source_path.read_text(encoding="utf-8").strip()
                previous_evaluation = best.evaluation
                last_screenshot = best.artifacts.generated_image
                self.logger.info(
                    "Iteration %s/%s: restored best-scoring source as edit base score=%s",
                    iteration,
                    self.settings.max_iterations,
                    best.score,
                )
            source_before = _source_tree_snapshot(source_root)
            interrupted_status: str | None = None
            self.logger.info(
                "Iteration %s/%s: asking coder agent to generate/edit HTML at %s",
                iteration,
                self.settings.max_iterations,
                source_path,
            )
            try:
                current_source = await self.coder.generate_html(
                    original_image_path=original_path,
                    source_path=source_path,
                    current_source=current_source,
                    previous_evaluation=previous_evaluation,
                    iteration_number=iteration,
                    previous_screenshot_path=last_screenshot,
                    user_note=request.user_note,
                )
            except Exception as exc:
                if not _is_agent_max_turns_exceeded(exc):
                    raise
                self.logger.warning(
                    "Iteration %s/%s: coder exceeded max turns; preserving renderable working source if available",
                    iteration,
                    self.settings.max_iterations,
                )
                if source_path.exists() and source_path.read_text(encoding="utf-8").strip():
                    current_source = source_path.read_text(encoding="utf-8")
                    interrupted_status = "agent_max_turns_reached"
                elif best is not None:
                    self.logger.warning(
                        "Iteration %s/%s: no renderable partial source; saving previous best score=%s",
                        iteration,
                        self.settings.max_iterations,
                        best.score,
                    )
                    return _job_result_from_best(
                        workspace=workspace,
                        job_id=request.job_id,
                        status="agent_max_turns_reached",
                        iterations=iteration - 1,
                        best=best,
                    )
                else:
                    raise
            current_source = _ensure_renderable_source(
                source_path=source_path,
                returned_source=current_source,
                iteration=iteration,
            )
            self.logger.info(
                "Iteration %s/%s: coder returned %s characters of HTML",
                iteration,
                self.settings.max_iterations,
                len(current_source),
            )
            if previous_evaluation is not None and source_before == _source_tree_snapshot(source_root):
                self.logger.warning(
                    "Iteration %s/%s: coder did not change working source; evaluation may repeat",
                    iteration,
                    self.settings.max_iterations,
                )
            screenshot_path = (
                self.screenshots_root / request.job_id / "iterations" / f"{iteration:03d}.png"
            )
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            self.logger.info(
                "Iteration %s/%s: rendering HTML screenshot to %s",
                iteration,
                self.settings.max_iterations,
                screenshot_path,
            )
            last_screenshot = await self.renderer.render(
                source_path=source_path,
                output_path=screenshot_path,
                viewport=viewport,
            )
            self.logger.info(
                "Iteration %s/%s: asking evaluator agent to compare images",
                iteration,
                self.settings.max_iterations,
            )
            evaluation = await self.evaluator.evaluate(
                original_image_path=original_path,
                generated_image_path=last_screenshot,
                user_note=request.user_note,
            )
            iteration_artifacts = workspace.save_iteration(
                number=iteration,
                source_html=current_source,
                source_root=source_root,
                generated_image=last_screenshot,
                evaluation=evaluation,
            )
            previous_evaluation = evaluation
            score = float(evaluation.get("score", 0.0))
            best = _new_best_iteration(
                current_best=best,
                artifacts=iteration_artifacts,
                evaluation=evaluation,
                score=score,
            )
            self.logger.info(
                "Iteration %s/%s: score=%s identical=%s critique=%s",
                iteration,
                self.settings.max_iterations,
                score,
                bool(evaluation.get("identical")),
                evaluation.get("critique", ""),
            )
            if interrupted_status is not None:
                self.logger.info(
                    "Iteration %s/%s: coder hit max turns; continuing after evaluating partial source",
                    iteration,
                    self.settings.max_iterations,
                )
            if score >= self.settings.target_score or bool(evaluation.get("identical")):
                self.logger.info(
                    "Iteration %s/%s: target reached, saving best-scoring final artifacts",
                    iteration,
                    self.settings.max_iterations,
                )
                assert best is not None
                return _job_result_from_best(
                    workspace=workspace,
                    job_id=request.job_id,
                    status="completed",
                    iterations=iteration,
                    best=best,
                )

        assert current_source is not None
        assert previous_evaluation is not None
        assert last_screenshot is not None
        assert best is not None
        self.logger.info(
            "Max iterations reached; saving best-scoring final artifacts with score=%s",
            best.score,
        )
        return _job_result_from_best(
            workspace=workspace,
            job_id=request.job_id,
            status="max_iterations_reached",
            iterations=self.settings.max_iterations,
            best=best,
        )


def _best_is_previous_iteration(best: BestIteration, iteration: int) -> bool:
    return best.artifacts.root.name == f"{iteration - 1:03d}"


def _new_best_iteration(
    *,
    current_best: BestIteration | None,
    artifacts: IterationArtifacts,
    evaluation: dict[str, Any],
    score: float,
) -> BestIteration:
    if current_best is not None and score <= current_best.score:
        return current_best
    return BestIteration(artifacts=artifacts, evaluation=evaluation, score=score)


def _job_result_from_best(
    *,
    workspace: JobWorkspace,
    job_id: str,
    status: str,
    iterations: int,
    best: BestIteration,
) -> JobResult:
    final = workspace.save_final_from_iteration(best.artifacts, best.evaluation)
    return JobResult(
        job_id=job_id,
        status=status,
        final_score=best.score,
        iterations=iterations,
        final_source_path=final.source,
        final_generated_image_path=final.generated_image,
        final_report_path=final.report,
        report=best.evaluation,
    )


def _restore_source_tree(*, source_root: Path, iteration: IterationArtifacts) -> None:
    if source_root.exists():
        shutil.rmtree(source_root)
    shutil.copytree(iteration.source_root, source_root)


def _source_tree_snapshot(source_root: Path) -> dict[str, str] | None:
    if not source_root.exists():
        return None
    return {
        str(path.relative_to(source_root)).replace("\\", "/"): path.read_text(encoding="utf-8")
        for path in sorted(source_root.rglob("*"))
        if path.is_file()
    }


def _ensure_renderable_source(
    *, source_path: Path, returned_source: str, iteration: int
) -> str:
    stripped_return = returned_source.strip()
    if not source_path.exists() and stripped_return.lower().startswith(("<!doctype", "<html")):
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(stripped_return, encoding="utf-8")

    if not source_path.exists():
        raise RuntimeError(
            "Coder did not create a renderable entrypoint at "
            f"{source_path} during iteration {iteration}. "
            "The model must write src/index.html or return complete HTML."
        )

    source = source_path.read_text(encoding="utf-8").strip()
    if not source:
        raise RuntimeError(
            "Coder created an empty renderable entrypoint at "
            f"{source_path} during iteration {iteration}."
        )
    return source


def _is_agent_max_turns_exceeded(exc: Exception) -> bool:
    try:
        from agents.exceptions import MaxTurnsExceeded
    except ModuleNotFoundError:
        return False
    return isinstance(exc, MaxTurnsExceeded)
