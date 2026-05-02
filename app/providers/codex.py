from __future__ import annotations

from typing import Any, Literal

from app.providers.codex_auth import codex_base_url, codex_headers, read_codex_tokens
from app.providers.codex_responses import (
    codex_continuation_attempts as _codex_continuation_attempts,
    codex_continuation_input as _codex_continuation_input,
    codex_needs_continuation as _codex_needs_continuation,
    consume_codex_event_stream as _consume_codex_event_stream,
    is_transient_stream_error as _is_transient_stream_error,
    log_codex_info as _log_info,
    log_codex_response_summary as _log_codex_response_summary,
    normalize_codex_final_response as _normalize_codex_final_response,
    response_with_streamed_text as _response_with_streamed_text,
    tool_call_from_leaked_text as _tool_call_from_leaked_text,
)


def build_codex_model(model_name: str) -> tuple[Any, Any]:
    try:
        from agents import AsyncOpenAI, ModelSettings
    except ModuleNotFoundError as exc:
        raise RuntimeError("Install the OpenAI Agents SDK package: openai-agents") from exc

    data = read_codex_tokens()
    access_token = str(data["tokens"]["access_token"])
    client = AsyncOpenAI(
        api_key=access_token,
        base_url=codex_base_url(),
        default_headers=codex_headers(access_token),
    )
    codex_model_class = _codex_streaming_responses_model_class()
    model = codex_model_class(model=model_name, openai_client=client)
    model_settings = ModelSettings(
        store=False,
        response_include=["reasoning.encrypted_content"],
    )
    return model, model_settings


def _codex_streaming_responses_model_class() -> type:
    try:
        from agents import OpenAIResponsesModel
    except ModuleNotFoundError as exc:
        raise RuntimeError("Install the OpenAI Agents SDK package: openai-agents") from exc

    class CodexStreamingResponsesModel(OpenAIResponsesModel):
        """Responses model adapter for chatgpt.com/backend-api/codex."""

        def _build_response_create_kwargs(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            create_kwargs = super()._build_response_create_kwargs(*args, **kwargs)
            create_kwargs["store"] = False
            create_kwargs.setdefault("reasoning", {"effort": "medium", "summary": "auto"})
            include = create_kwargs.get("include")
            if isinstance(include, list):
                if "reasoning.encrypted_content" not in include:
                    include.append("reasoning.encrypted_content")
            else:
                create_kwargs["include"] = ["reasoning.encrypted_content"]

            # The Codex backend rejects omitted optional Responses values when
            # they are serialized as null. Keep this request close to codex-rs.
            if create_kwargs.get("max_output_tokens") is None:
                create_kwargs.pop("max_output_tokens", None)
            return create_kwargs

        async def _fetch_response(
            self,
            system_instructions: str | None,
            input: Any,
            model_settings: Any,
            tools: list[Any],
            output_schema: Any | None,
            handoffs: list[Any],
            previous_response_id: str | None = None,
            conversation_id: str | None = None,
            stream: Literal[True] | Literal[False] = False,
            prompt: Any | None = None,
        ) -> Any:
            if stream:
                return await super()._fetch_response(
                    system_instructions,
                    input,
                    model_settings,
                    tools,
                    output_schema,
                    handoffs,
                    previous_response_id=previous_response_id,
                    conversation_id=conversation_id,
                    stream=True,
                    prompt=prompt,
                )

            current_input = input
            max_attempts = _codex_continuation_attempts()
            for attempt in range(1, max_attempts + 1):
                event_stream = await super()._fetch_response(
                    system_instructions,
                    current_input,
                    model_settings,
                    tools,
                    output_schema,
                    handoffs,
                    previous_response_id=previous_response_id,
                    conversation_id=conversation_id,
                    stream=True,
                    prompt=prompt,
                )
                try:
                    final_response, streamed_text = await _consume_codex_event_stream(event_stream)
                except Exception as exc:
                    if attempt < max_attempts and _is_transient_stream_error(exc):
                        _log_info(
                            "Codex stream interrupted before a final response "
                            "(attempt %d/%d); retrying request: %s",
                            attempt,
                            max_attempts,
                            exc,
                        )
                        continue
                    raise
                if final_response is None:
                    if streamed_text.strip():
                        final_response = _response_with_streamed_text(streamed_text.strip())
                    else:
                        raise RuntimeError(
                            "Codex streaming response ended without a final response."
                        )
                response = _normalize_codex_final_response(
                    final_response,
                    streamed_text=streamed_text,
                )
                _log_codex_response_summary(response, streamed_text=streamed_text, attempt=attempt)
                if not _codex_needs_continuation(response) or attempt >= max_attempts:
                    return response
                _log_info(
                    "Codex response needs continuation (attempt %d/%d); asking Codex to "
                    "finish the same turn.",
                    attempt,
                    max_attempts,
                )
                current_input = _codex_continuation_input(current_input, response)

            raise RuntimeError("Codex streaming response did not produce a usable response.")

    return CodexStreamingResponsesModel
