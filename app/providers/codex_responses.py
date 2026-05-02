from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from app.job_logging import current_job_logger


logger = logging.getLogger(__name__)

_TOOL_CALL_LEAK_PATTERN = re.compile(
    r"(?:^|[\s>|])to=functions\.([A-Za-z_][\w.]*)",
    re.IGNORECASE,
)


async def consume_codex_event_stream(event_stream: Any) -> tuple[Any | None, str]:
    final_response = None
    streamed_chunks: list[str] = []
    output_items: list[Any] = []
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
            elif event_type == "response.output_item.done":
                item = getattr(event, "item", None)
                if item is not None:
                    output_items.append(item)

            response = getattr(event, "response", None)
            if (
                event_type in {"response.completed", "response.failed", "response.incomplete"}
                and response is not None
            ):
                final_response = response
    except Exception as exc:
        if is_transient_stream_error(exc) and streamed_chunks:
            log_codex_info(
                "Codex stream interrupted after %d streamed chars; using streamed text "
                "backfill: %s",
                sum(len(chunk) for chunk in streamed_chunks),
                exc,
            )
            return None, "".join(streamed_chunks)
        raise
    if final_response is not None:
        output = getattr(final_response, "output", None)
        if isinstance(output, list) and not output and output_items:
            final_response.output = list(output_items)
            log_codex_info(
                "Codex stream backfilled %d output item(s) from output_item.done events.",
                len(output_items),
            )
    return final_response, "".join(streamed_chunks)


def normalize_codex_final_response(response: Any, *, streamed_text: str = "") -> Any:
    output = getattr(response, "output", None)
    if not isinstance(output, list):
        output = []
    if not output:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            response.output = [response_message(output_text.strip())]
            return response
        if streamed_text.strip():
            response.output = [response_message(streamed_text.strip())]
            return response

    normalized_output: list[Any] = []
    for item in output:
        text = message_text(item)
        leaked_call = tool_call_from_leaked_text(text)
        if leaked_call is not None:
            normalized_output.append(leaked_call)
            continue
        normalized_output.append(item)
    response.output = normalized_output
    if (
        not response_visible_text(response)
        and streamed_text.strip()
        and not response_has_tool_call(response)
    ):
        response.output = [response_message(streamed_text.strip())]
    return response


def codex_needs_continuation(response: Any) -> bool:
    if response_has_tool_call(response):
        return False
    if response_visible_text(response):
        return False

    status = getattr(response, "status", None)
    normalized_status = status.strip().lower() if isinstance(status, str) else None
    if isinstance(status, str) and status.strip().lower() in {
        "queued",
        "in_progress",
        "incomplete",
    }:
        return True

    output = getattr(response, "output", None)
    if not isinstance(output, list):
        return True
    if not output:
        return normalized_status != "completed"

    saw_commentary_or_analysis = False
    saw_final = False
    saw_reasoning = False
    for item in output:
        item_type = item_type_name(item)
        if item_type == "reasoning":
            saw_reasoning = True
            continue
        if item_type != "message":
            continue
        phase = item_value(item, "phase")
        if isinstance(phase, str):
            normalized_phase = phase.strip().lower()
            if normalized_phase in {"commentary", "analysis"}:
                saw_commentary_or_analysis = True
            elif normalized_phase in {"final", "final_answer"}:
                saw_final = True
    return saw_reasoning or (saw_commentary_or_analysis and not saw_final)


def codex_continuation_input(original_input: Any, response: Any) -> list[Any]:
    if isinstance(original_input, list):
        items = [wire_dict(item) for item in original_input]
    elif isinstance(original_input, str):
        items = [{"role": "user", "content": original_input}]
    else:
        items = [{"role": "user", "content": str(original_input)}]

    appended_reasoning_without_following_item = False
    for item in getattr(response, "output", None) or []:
        replay_item = replayable_codex_output_item(item)
        if replay_item is not None:
            items.append(replay_item)
            appended_reasoning_without_following_item = replay_item.get("type") == "reasoning"
            continue
        if appended_reasoning_without_following_item:
            appended_reasoning_without_following_item = False

    if appended_reasoning_without_following_item:
        items.append({"role": "assistant", "content": ""})

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


def replayable_codex_output_item(item: Any) -> dict[str, Any] | None:
    item_type = item_type_name(item)
    if item_type == "reasoning":
        encrypted = item_value(item, "encrypted_content")
        if isinstance(encrypted, str) and encrypted:
            replay = {"type": "reasoning", "encrypted_content": encrypted}
            summary = item_value(item, "summary")
            if summary:
                replay["summary"] = wire_dict(summary)
            return replay
        return None
    if item_type == "message":
        replay = wire_dict(item)
        if replay.get("type") != "message":
            replay["type"] = "message"
        replay.setdefault("role", "assistant")
        replay.setdefault("status", "completed")
        return replay
    return None


def response_has_tool_call(response: Any) -> bool:
    for item in getattr(response, "output", None) or []:
        if item_type_name(item) in {"function_call", "custom_tool_call"}:
            return True
    return False


def response_visible_text(response: Any) -> str:
    chunks = [message_text(item) for item in getattr(response, "output", None) or []]
    text = "\n".join(chunk for chunk in chunks if chunk).strip()
    if text:
        return text
    output_text = getattr(response, "output_text", None)
    return output_text.strip() if isinstance(output_text, str) else ""


def log_codex_response_summary(response: Any, *, streamed_text: str, attempt: int) -> None:
    output = getattr(response, "output", None)
    output = output if isinstance(output, list) else []
    item_types = [item_type_name(item) or type(item).__name__ for item in output]
    text = response_visible_text(response)
    status = getattr(response, "status", None)
    log_codex_info(
        "Codex response attempt=%d status=%s output_types=%s text_chars=%d "
        "streamed_chars=%d has_tool_call=%s",
        attempt,
        status,
        item_types,
        len(text),
        len(streamed_text or ""),
        response_has_tool_call(response),
    )
    if text:
        log_codex_info("Codex response text preview: %s", one_line_preview(text))


def response_with_streamed_text(text: str) -> Any:
    try:
        from openai.types.responses import Response
    except ModuleNotFoundError:
        return type(
            "CodexStreamBackfillResponse",
            (),
            {
                "id": "resp_codex_stream_backfill",
                "status": "completed",
                "output": [response_message(text)],
                "usage": None,
            },
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
        output=[response_message(text)],
        parallel_tool_calls=True,
        temperature=None,
        tool_choice="auto",
        tools=[],
        top_p=None,
        status="completed",
        usage=None,
    )


def message_text(item: Any) -> str:
    if item_type_name(item) != "message":
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


def tool_call_from_leaked_text(text: str) -> Any | None:
    match = _TOOL_CALL_LEAK_PATTERN.search(text or "")
    if match is None:
        return None
    name = match.group(1)
    raw_args = json_object_after(text, match.end()) or "{}"
    try:
        json.loads(raw_args)
    except Exception:
        raw_args = "{}"
    call_id = deterministic_call_id(name, raw_args)
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


def json_object_after(text: str, start: int) -> str | None:
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


def response_message(text: str) -> Any:
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


def item_type_name(item: Any) -> str | None:
    if isinstance(item, dict):
        value = item.get("type")
    else:
        value = getattr(item, "type", None)
    return value if isinstance(value, str) else None


def item_value(item: Any, key: str) -> Any:
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def wire_dict(value: Any) -> Any:
    if isinstance(value, list):
        return [wire_dict(item) for item in value]
    if isinstance(value, dict):
        return {str(key): wire_dict(item) for key, item in value.items() if item is not None}
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json", exclude_none=True)
    if hasattr(value, "__dict__"):
        return {
            str(key): wire_dict(item)
            for key, item in vars(value).items()
            if not key.startswith("_") and item is not None
        }
    return value


def one_line_preview(text: str, limit: int = 500) -> str:
    preview = re.sub(r"\s+", " ", text).strip()
    if len(preview) <= limit:
        return preview
    return f"{preview[:limit]}..."


def codex_continuation_attempts() -> int:
    raw = os.getenv("CODEX_CONTINUATION_ATTEMPTS", "").strip()
    if not raw:
        return 3
    try:
        return max(1, min(6, int(raw)))
    except ValueError:
        return 3


def is_transient_stream_error(exc: Exception) -> bool:
    name = exc.__class__.__name__
    module = exc.__class__.__module__
    return name in {"RemoteProtocolError", "ReadError", "ReadTimeout"} or (
        "httpx" in module and "incomplete chunked read" in str(exc).lower()
    )


def log_codex_info(message: str, *args: Any) -> None:
    job_logger = current_job_logger()
    if job_logger is not None:
        job_logger.info(message, *args)
    else:
        logger.info(message, *args)


def deterministic_call_id(name: str, arguments: str) -> str:
    import hashlib

    digest = hashlib.sha256(f"{name}:{arguments}".encode("utf-8")).hexdigest()[:12]
    return f"call_{digest}"
