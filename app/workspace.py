from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class IterationArtifacts:
    root: Path
    source: Path
    generated_image: Path
    evaluation: Path


@dataclass(frozen=True)
class FinalArtifacts:
    root: Path
    source: Path
    generated_image: Path
    report: Path


@dataclass(frozen=True)
class JobWorkspace:
    root: Path

    @classmethod
    def create(cls, workspaces_root: Path, job_id: str) -> "JobWorkspace":
        root = workspaces_root / job_id
        (root / "iterations").mkdir(parents=True, exist_ok=True)
        (root / "final").mkdir(parents=True, exist_ok=True)
        return cls(root=root)

    def save_original_image(self, image_bytes: bytes, extension: str) -> Path:
        normalized = extension if extension.startswith(".") else f".{extension}"
        path = self.root / f"original_image{normalized.lower()}"
        path.write_bytes(image_bytes)
        return path

    def save_iteration(
        self,
        *,
        number: int,
        source_html: str,
        generated_image: bytes | Path,
        evaluation: dict[str, Any],
    ) -> IterationArtifacts:
        root = self.root / "iterations" / f"{number:03d}"
        root.mkdir(parents=True, exist_ok=True)
        source = root / "source.html"
        generated = root / "generated_image.png"
        evaluation_path = root / "evaluation.json"

        source.write_text(source_html, encoding="utf-8")
        if isinstance(generated_image, Path):
            generated.write_bytes(generated_image.read_bytes())
        else:
            generated.write_bytes(generated_image)
        evaluation_path.write_text(
            json.dumps(evaluation, indent=2, sort_keys=True), encoding="utf-8"
        )
        return IterationArtifacts(root=root, source=source, generated_image=generated, evaluation=evaluation_path)

    def save_final(
        self,
        *,
        source_html: str,
        generated_image: bytes | Path,
        report: dict[str, Any],
    ) -> FinalArtifacts:
        root = self.root / "final"
        root.mkdir(parents=True, exist_ok=True)
        source = root / "source.html"
        generated = root / "generated_image.png"
        report_path = root / "report.json"

        source.write_text(source_html, encoding="utf-8")
        if isinstance(generated_image, Path):
            generated.write_bytes(generated_image.read_bytes())
        else:
            generated.write_bytes(generated_image)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        return FinalArtifacts(root=root, source=source, generated_image=generated, report=report_path)

