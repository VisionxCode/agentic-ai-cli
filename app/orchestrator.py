from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.workspace import JobWorkspace


class Coder(Protocol):
    async def generate_html(
        self,
        *,
        original_image_path: Path,
        current_source: str | None,
        previous_evaluation: dict[str, Any] | None,
    ) -> str: ...


class Evaluator(Protocol):
    async def evaluate(
        self, *, original_image_path: Path, generated_image_path: Path
    ) -> dict[str, Any]: ...


class Renderer(Protocol):
    async def render(self, *, source_html: str, output_path: Path, viewport: dict[str, int]) -> Path: ...


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
        coder: Coder,
        evaluator: Evaluator,
        renderer: Renderer,
        settings: RunSettings,
    ) -> None:
        self.workspaces_root = workspaces_root
        self.coder = coder
        self.evaluator = evaluator
        self.renderer = renderer
        self.settings = settings

    async def run(self, request: JobRequest) -> JobResult:
        workspace = JobWorkspace.create(self.workspaces_root, request.job_id)
        original_path = workspace.save_original_image(request.image_bytes, request.image_extension)
        viewport = self.settings.viewport or {"width": 1440, "height": 900}

        current_source: str | None = None
        previous_evaluation: dict[str, Any] | None = None
        last_screenshot: Path | None = None

        for iteration in range(1, self.settings.max_iterations + 1):
            current_source = await self.coder.generate_html(
                original_image_path=original_path,
                current_source=current_source,
                previous_evaluation=previous_evaluation,
            )
            screenshot_path = workspace.root / "iterations" / f"{iteration:03d}" / "generated_image.png"
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            last_screenshot = await self.renderer.render(
                source_html=current_source,
                output_path=screenshot_path,
                viewport=viewport,
            )
            evaluation = await self.evaluator.evaluate(
                original_image_path=original_path,
                generated_image_path=last_screenshot,
            )
            workspace.save_iteration(
                number=iteration,
                source_html=current_source,
                generated_image=last_screenshot,
                evaluation=evaluation,
            )
            previous_evaluation = evaluation
            score = float(evaluation.get("score", 0.0))
            if score >= self.settings.target_score or bool(evaluation.get("identical")):
                final = workspace.save_final(
                    source_html=current_source,
                    generated_image=last_screenshot,
                    report=evaluation,
                )
                return JobResult(
                    job_id=request.job_id,
                    status="completed",
                    final_score=score,
                    iterations=iteration,
                    final_source_path=final.source,
                    final_generated_image_path=final.generated_image,
                    final_report_path=final.report,
                    report=evaluation,
                )

        assert current_source is not None
        assert previous_evaluation is not None
        assert last_screenshot is not None
        final = workspace.save_final(
            source_html=current_source,
            generated_image=last_screenshot,
            report=previous_evaluation,
        )
        return JobResult(
            job_id=request.job_id,
            status="max_iterations_reached",
            final_score=float(previous_evaluation.get("score", 0.0)),
            iterations=self.settings.max_iterations,
            final_source_path=final.source,
            final_generated_image_path=final.generated_image,
            final_report_path=final.report,
            report=previous_evaluation,
        )

