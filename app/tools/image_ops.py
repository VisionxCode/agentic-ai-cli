from __future__ import annotations

from pathlib import Path


def image_dimensions(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.size
    except ModuleNotFoundError as exc:
        raise RuntimeError("Install Pillow to inspect image dimensions") from exc


def ensure_supported_image(path: Path) -> Path:
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError(f"Unsupported image type: {path.suffix}")
    if not path.exists():
        raise FileNotFoundError(path)
    return path

