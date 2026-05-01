from __future__ import annotations

import logging


KNOWN_VISION_MODELS = {
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "google/gemini-2.5-pro",
    "google/gemini-2.5-flash",
    "anthropic/claude-sonnet-4.5",
    "anthropic/claude-haiku-4.5",
}

KNOWN_TEXT_ONLY_MODELS = {
    "xiaomi/mimo-v2.5-pro",
}


def validate_image_input_models(
    models: dict[str, str], logger: logging.Logger | None = None
) -> None:
    for agent_name, model_name in models.items():
        normalized = model_name.strip()
        if normalized in KNOWN_TEXT_ONLY_MODELS:
            raise ValueError(
                f"{agent_name} model '{normalized}' does not support image input. "
                "This workflow sends images through OpenAI Agents SDK input_image payloads, "
                "so choose a vision-capable OpenRouter model such as openai/gpt-4o."
            )
        if normalized not in KNOWN_VISION_MODELS and logger is not None:
            logger.warning(
                "Model %s for %s is not in the local vision allowlist; OpenRouter may reject "
                "image inputs if the model architecture lacks image modality support.",
                normalized,
                agent_name,
            )
