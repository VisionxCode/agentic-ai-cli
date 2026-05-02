from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.workspace import IterationArtifacts, JobWorkspace


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
    ) -> str: ...


class Evaluator(Protocol):
    async def evaluate(
        self, *, original_image_path: Path, generated_image_path: Path
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
        viewport = self.settings.viewport or {"width": 1440, "height": 900}
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
        best_iteration: IterationArtifacts | None = None
        best_evaluation: dict[str, Any] | None = None
        best_score = float("-inf")
        source_root = workspace.root / "working" / "src"
        source_path = source_root / "index.html"
        source_path.parent.mkdir(parents=True, exist_ok=True)

        for iteration in range(1, self.settings.max_iterations + 1):
            source_before = _source_tree_snapshot(source_root)
            self.logger.info(
                "Iteration %s/%s: asking coder agent to generate/edit HTML at %s",
                iteration,
                self.settings.max_iterations,
                source_path,
            )
            current_source = await self.coder.generate_html(
                original_image_path=original_path,
                source_path=source_path,
                current_source=current_source,
                previous_evaluation=previous_evaluation,
                iteration_number=iteration,
                previous_screenshot_path=last_screenshot,
            )
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
            if score > best_score:
                best_iteration = iteration_artifacts
                best_evaluation = evaluation
                best_score = score
            self.logger.info(
                "Iteration %s/%s: score=%s identical=%s critique=%s",
                iteration,
                self.settings.max_iterations,
                score,
                bool(evaluation.get("identical")),
                evaluation.get("critique", ""),
            )
            if score >= self.settings.target_score or bool(evaluation.get("identical")):
                self.logger.info(
                    "Iteration %s/%s: target reached, saving best-scoring final artifacts",
                    iteration,
                    self.settings.max_iterations,
                )
                assert best_iteration is not None
                assert best_evaluation is not None
                final = workspace.save_final_from_iteration(best_iteration, best_evaluation)
                return JobResult(
                    job_id=request.job_id,
                    status="completed",
                    final_score=best_score,
                    iterations=iteration,
                    final_source_path=final.source,
                    final_generated_image_path=final.generated_image,
                    final_report_path=final.report,
                    report=best_evaluation,
                )

        assert current_source is not None
        assert previous_evaluation is not None
        assert last_screenshot is not None
        assert best_iteration is not None
        assert best_evaluation is not None
        self.logger.info(
            "Max iterations reached; saving best-scoring final artifacts with score=%s",
            best_score,
        )
        final = workspace.save_final_from_iteration(best_iteration, best_evaluation)
        return JobResult(
            job_id=request.job_id,
            status="max_iterations_reached",
            final_score=best_score,
            iterations=self.settings.max_iterations,
            final_source_path=final.source,
            final_generated_image_path=final.generated_image,
            final_report_path=final.report,
            report=best_evaluation,
        )


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
