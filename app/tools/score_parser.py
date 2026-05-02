from __future__ import annotations

import json
from typing import Any


class EvaluationParseError(ValueError):
    """Raised when evaluator output is not the required JSON shape."""


REQUIRED_FIELDS = {
    "score": (int, float),
    "identical": bool,
    "critique": str,
    "missing_details": list,
    "revision_instructions": list,
}


def _extract_json_object(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    decoder = json.JSONDecoder()
    first_decode_error: json.JSONDecodeError | None = None
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            _, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError as exc:
            first_decode_error = first_decode_error or exc
            continue
        return text[index : index + end]
    if first_decode_error is not None:
        raise EvaluationParseError(f"Invalid evaluator JSON: {first_decode_error}") from first_decode_error
    raise EvaluationParseError("Evaluator output did not contain a JSON object")


def parse_evaluation(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        data = raw
    else:
        try:
            data = json.loads(_extract_json_object(raw))
        except json.JSONDecodeError as exc:
            raise EvaluationParseError(f"Invalid evaluator JSON: {exc}") from exc

    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in data:
            raise EvaluationParseError(f"Missing evaluator field: {field}")
        if not isinstance(data[field], expected_type):
            raise EvaluationParseError(f"Evaluator field '{field}' has the wrong type")

    score = float(data["score"])
    if not 0.0 <= score <= 1.0:
        raise EvaluationParseError("Evaluator score must be between 0 and 1")
    data["score"] = score

    for field in ("missing_details", "revision_instructions"):
        if not all(isinstance(item, str) for item in data[field]):
            raise EvaluationParseError(f"Evaluator field '{field}' must contain strings")

    return data
