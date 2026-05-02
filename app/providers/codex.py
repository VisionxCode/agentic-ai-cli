from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Literal

from app.job_logging import current_job_logger
from app.providers.codex_auth import codex_base_url, codex_headers, read_codex_tokens


logger = logging.getLogger(__name__)

_TOOL_CALL_LEAK_PATTERN = re.compile(
    r"(?:^|[\s>|])to=functions\.([A-Za-z_][\w.]*)",
    re.IGNORECASE,
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
        """Responses model for chatgpt.com/backend-api/codex.

        The Codex backend rejects non-streaming Responses calls with
        "Stream must be set to true". The Agents runner normally calls
        get_response(), so this adapter forces streaming for that internal call
        and returns the completed response object to the SDK.
        """

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

            # Codex backend currently rejects some normal Responses optional
            # parameters. Drop omitted/empty values and keep the wire shape
            # close to codex-rs/Hermes.
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
                            "Codex stream interrupted before a final response (attempt %d/%d); retrying request: %s",
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
                        raise RuntimeError("Codex streaming response ended without a final response.")
                response = _normalize_codex_final_response(final_response, streamed_text=streamed_text)
                _log_codex_response_summary(response, streamed_text=streamed_text, attempt=attempt)
                if not _codex_needs_continuation(response) or attempt >= max_attempts:
                    return response
                _log_info(
                    "Codex response needs continuation (attempt %d/%d); asking Codex to finish the same turn.",
                    attempt,
                    max_attempts,
                )
                current_input = _codex_continuation_input(current_input, response)

            raise RuntimeError("Codex streaming response did not produce a usable response.")

    return CodexStreamingResponsesModel


async def _consume_codex_event_stream(event_stream: Any) -> tuple[Any | None, str]:
    final_response = None
    streamed_chunks: list[str] = []
    try:
        async for event in event_stream:
            event_type = getattr(event, "type", None)
            delta = getattr(event, "delta", None)
            text = getattr(event, "text", None)
            if event_type in {
                "response.output_text.delta",
                "response.refusal.delta",
                "response.reasoning_summary_text.delta",
            }:
                if isinstance(delta, str):
                    streamed_chunks.append(delta)
                elif isinstance(text, str):
                    streamed_chunks.append(text)
            elif event_type in {"response.output_text.done", "response.content_part.done"}:
                if isinstance(text, str):
                    streamed_chunks.append(text)
                part = getattr(event, "part", None)
                part_text = getattr(part, "text", None)
                if isinstance(part_text, str):
                    streamed_chunks.append(part_text)

            response = getattr(event, "response", None)
            if event_type in {"response.completed", "response.failed", "response.incomplete"} and response is not None:
                final_response = response
    except Exception as exc:
        if _is_transient_stream_error(exc) and streamed_chunks:
            _log_info(
                "Codex stream interrupted after %d streamed chars; using streamed text backfill: %s",
                sum(len(chunk) for chunk in streamed_chunks),
                exc,
            )
            return None, "".join(streamed_chunks)
        raise
    return final_response, "".join(streamed_chunks)


def _normalize_codex_final_response(response: Any, *, streamed_text: str = "") -> Any:
    output = getattr(response, "output", None)
    if not isinstance(output, list):
        output = []
    if not output:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            response.output = [_response_message(output_text.strip())]
            return response
        if streamed_text.strip():
            response.output = [_response_message(streamed_text.strip())]
            return response

    normalized_output: list[Any] = []
    for item in output:
        text = _message_text(item)
        leaked_call = _tool_call_from_leaked_text(text)
        if leaked_call is not None:
            normalized_output.append(leaked_call)
            continue
        normalized_output.append(item)
    response.output = normalized_output
    if not _response_visible_text(response) and streamed_text.strip() and not _response_has_tool_call(response):
        response.output = [_response_message(streamed_text.strip())]
    return response


def _codex_needs_continuation(response: Any) -> bool:
    if _response_has_tool_call(response):
        return False
    if _response_visible_text(response):
        return False

    status = getattr(response, "status", None)
    if isinstance(status, str) and status.strip().lower() in {"queued", "in_progress", "incomplete"}:
        return True

    output = getattr(response, "output", None)
    if not isinstance(output, list) or not output:
        return True

    saw_commentary_or_analysis = False
    saw_final = False
    saw_reasoning = False
    for item in output:
        item_type = _item_type(item)
        if item_type == "reasoning":
            saw_reasoning = True
            continue
        if item_type != "message":
            continue
        phase = _item_value(item, "phase")
        if isinstance(phase, str):
            normalized_phase = phase.strip().lower()
            if normalized_phase in {"commentary", "analysis"}:
                saw_commentary_or_analysis = True
            elif normalized_phase in {"final", "final_answer"}:
                saw_final = True
    return saw_reasoning or (saw_commentary_or_analysis and not saw_final)


def _codex_continuation_input(original_input: Any, response: Any) -> list[Any]:
    items: list[Any]
    if isinstance(original_input, list):
        items = [_wire_dict(item) for item in original_input]
    elif isinstance(original_input, str):
        items = [{"role": "user", "content": original_input}]
    else:
        items = [{"role": "user", "content": str(original_input)}]

    for item in getattr(response, "output", None) or []:
        replay_item = _replayable_codex_output_item(item)
        if replay_item is not None:
            items.append(replay_item)

    items.append(
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "Continue the same turn and finish with either a structured tool call "
                        "or the final answer. Do not repeat prior reasoning-only content."
                    ),
                }
            ],
        }
    )
    return items


def _replayable_codex_output_item(item: Any) -> dict[str, Any] | None:
    item_type = _item_type(item)
    if item_type == "reasoning":
        encrypted = _item_value(item, "encrypted_content")
        if isinstance(encrypted, str) and encrypted:
            replay = {"type": "reasoning", "encrypted_content": encrypted}
            summary = _item_value(item, "summary")
            if summary:
                replay["summary"] = _wire_dict(summary)
            return replay
        return None
    if item_type == "message":
        replay = _wire_dict(item)
        if replay.get("type") != "message":
            replay["type"] = "message"
        replay.setdefault("role", "assistant")
        replay.setdefault("status", "completed")
        return replay
    return None


def _response_has_tool_call(response: Any) -> bool:
    for item in getattr(response, "output", None) or []:
        if _item_type(item) in {"function_call", "custom_tool_call"}:
            return True
    return False


def _response_visible_text(response: Any) -> str:
    chunks = [_message_text(item) for item in getattr(response, "output", None) or []]
    text = "\n".join(chunk for chunk in chunks if chunk).strip()
    if text:
        return text
    output_text = getattr(response, "output_text", None)
    return output_text.strip() if isinstance(output_text, str) else ""


def _log_codex_response_summary(response: Any, *, streamed_text: str, attempt: int) -> None:
    output = getattr(response, "output", None)
    output = output if isinstance(output, list) else []
    item_types = [_item_type(item) or type(item).__name__ for item in output]
    text = _response_visible_text(response)
    status = getattr(response, "status", None)
    _log_info(
        "Codex response attempt=%d status=%s output_types=%s text_chars=%d streamed_chars=%d has_tool_call=%s",
        attempt,
        status,
        item_types,
        len(text),
        len(streamed_text or ""),
        _response_has_tool_call(response),
    )
    if text:
        _log_info("Codex response text preview: %s", _one_line_preview(text))


def _response_with_streamed_text(text: str) -> Any:
    try:
        from openai.types.responses import Response
    except ModuleNotFoundError:
        return type(
            "CodexStreamBackfillResponse",
            (),
            {"id": "resp_codex_stream_backfill", "status": "completed", "output": [_response_message(text)], "usage": None},
        )()
    return Response(
        id="resp_codex_stream_backfill",
        created_at=0.0,
        error=None,
        incomplete_details=None,
        instructions=None,
        metadata={},
        model="codex",
        object="response",
        output=[_response_message(text)],
        parallel_tool_calls=True,
        temperature=None,
        tool_choice="auto",
        tools=[],
        top_p=None,
        status="completed",
        usage=None,
    )


def _message_text(item: Any) -> str:
    if _item_type(item) != "message":
        return ""
    content = getattr(item, "content", None)
    if isinstance(item, dict):
        content = item.get("content")
    if not isinstance(content, list):
        return ""
    chunks: list[str] = []
    for part in content:
        part_type = getattr(part, "type", None)
        text = getattr(part, "text", None)
        if isinstance(part, dict):
            part_type = part.get("type")
            text = part.get("text")
        if part_type in {"output_text", "text"} and isinstance(text, str):
            chunks.append(text)
    return "\n".join(chunks).strip()


def _tool_call_from_leaked_text(text: str) -> Any | None:
    match = _TOOL_CALL_LEAK_PATTERN.search(text or "")
    if match is None:
        return None
    name = match.group(1)
    raw_args = _json_object_after(text, match.end()) or "{}"
    try:
        json.loads(raw_args)
    except Exception:
        raw_args = "{}"
    call_id = _deterministic_call_id(name, raw_args)
    try:
        from openai.types.responses import ResponseFunctionToolCall
    except ModuleNotFoundError:
        return {
            "type": "function_call",
            "name": name,
            "arguments": raw_args,
            "call_id": call_id,
            "id": f"fc_{call_id.removeprefix('call_')}",
        }
    return ResponseFunctionToolCall(
        type="function_call",
        name=name,
        arguments=raw_args,
        call_id=call_id,
        id=f"fc_{call_id.removeprefix('call_')}",
        status="completed",
    )


def _json_object_after(text: str, start: int) -> str | None:
    brace_start = text.find("{", start)
    if brace_start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(brace_start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[brace_start : index + 1]
    return None


def _response_message(text: str) -> Any:
    try:
        from openai.types.responses import ResponseOutputMessage, ResponseOutputText
    except ModuleNotFoundError:
        return {
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": text}],
        }
    return ResponseOutputMessage(
        id="msg_codex_output_text_fallback",
        type="message",
        role="assistant",
        status="completed",
        content=[
            ResponseOutputText(
                type="output_text",
                text=text,
                annotations=[],
            )
        ],
    )


def _item_type(item: Any) -> str | None:
    if isinstance(item, dict):
        value = item.get("type")
    else:
        value = getattr(item, "type", None)
    return value if isinstance(value, str) else None


def _item_value(item: Any, key: str) -> Any:
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _wire_dict(value: Any) -> Any:
    if isinstance(value, list):
        return [_wire_dict(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _wire_dict(item) for key, item in value.items() if item is not None}
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json", exclude_none=True)
    if hasattr(value, "__dict__"):
        return {
            str(key): _wire_dict(item)
            for key, item in vars(value).items()
            if not key.startswith("_") and item is not None
        }
    return value


def _one_line_preview(text: str, limit: int = 500) -> str:
    preview = re.sub(r"\s+", " ", text).strip()
    if len(preview) <= limit:
        return preview
    return f"{preview[:limit]}..."


def _codex_continuation_attempts() -> int:
    raw = os.getenv("CODEX_CONTINUATION_ATTEMPTS", "").strip()
    if not raw:
        return 3
    try:
        return max(1, min(6, int(raw)))
    except ValueError:
        return 3


def _is_transient_stream_error(exc: Exception) -> bool:
    name = exc.__class__.__name__
    module = exc.__class__.__module__
    return name in {"RemoteProtocolError", "ReadError", "ReadTimeout"} or (
        "httpx" in module and "incomplete chunked read" in str(exc).lower()
    )


def _log_info(message: str, *args: Any) -> None:
    job_logger = current_job_logger()
    if job_logger is not None:
        job_logger.info(message, *args)
    else:
        logger.info(message, *args)


def _deterministic_call_id(name: str, arguments: str) -> str:
    import hashlib

    digest = hashlib.sha256(f"{name}:{arguments}".encode("utf-8")).hexdigest()[:12]
    return f"call_{digest}"
