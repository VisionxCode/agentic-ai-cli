from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Sequence

from app.orchestrator import JobResult
from app.runtime import log_path_for, run_job_from_image_path


def _display_path(path: Path) -> str:
    return path.as_posix()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.main",
        description="Run the image-to-source-code agent workflow for one image.",
    )
    parser.add_argument("--image", required=True, help="Path to the original image.")
    parser.add_argument("--note", default=None, help="Optional guidance for the coder and evaluator.")
    parser.add_argument("--job-id", default=None, help="Optional job id for deterministic artifact paths.")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print JSON output.")
    return parser


def result_to_dict(result: JobResult) -> dict[str, object]:
    return {
        "job_id": result.job_id,
        "status": result.status,
        "final_score": result.final_score,
        "iterations": result.iterations,
        "final_source_path": _display_path(result.final_source_path),
        "final_generated_image_path": _display_path(result.final_generated_image_path),
        "final_report_path": _display_path(result.final_report_path),
        "log_path": _display_path(log_path_for(result.job_id)),
    }


def print_text_summary(result: JobResult) -> None:
    for key, value in result_to_dict(result).items():
        print(f"{key}: {value}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"Image path does not exist: {image_path}", file=sys.stderr)
        return 2
    if not image_path.is_file():
        print(f"Image path is not a file: {image_path}", file=sys.stderr)
        return 2

    try:
        result = asyncio.run(
            run_job_from_image_path(
                image_path=image_path,
                user_note=args.note,
                job_id=args.job_id,
            )
        )
    except Exception as exc:
        print(f"Job failed: {exc}", file=sys.stderr)
        return 1

    if args.json_output:
        print(json.dumps(result_to_dict(result), indent=2, sort_keys=True))
    else:
        print_text_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
