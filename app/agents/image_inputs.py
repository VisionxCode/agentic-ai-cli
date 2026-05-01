from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Any, Literal


ImageDetail = Literal["low", "high", "auto", "original"]


def image_input_from_path(path: Path, *, detail: ImageDetail = "auto") -> dict[str, str]:
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        "type": "input_image",
        "image_url": f"data:{mime_type};base64,{encoded}",
        "detail": detail,
    }


def user_message_with_content(content: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "role": "user",
            "content": content,
        }
    ]


def text_input(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "type": "input_text",
        "text": json.dumps(payload),
    }
