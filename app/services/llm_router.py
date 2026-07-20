"""OpenRouter-backed LLM query service (MVP-NFR-3). Framework-agnostic: plain
functions/enum over an injected httpx.AsyncClient, no FastAPI imports, no
config lookups of its own.

Provider abstraction: `LLMModel` member names (FAST/CAPABLE) and `query()` are
the only things callers should ever touch. OpenRouter's base URL, auth header
shape, request/response wire format, and SSE parsing are private to this
module — if the provider changes later, only this file changes.

See blueprints/plans/features/openrouter-integration.md for the full spec.
"""

import json
from collections.abc import AsyncIterator
from enum import StrEnum
from typing import Literal, TypeVar

import httpx
from pydantic import BaseModel

_BASE_URL = "https://openrouter.ai/api/v1"

BaseModelT = TypeVar("BaseModelT", bound=BaseModel)


class LLMModel(StrEnum):
    FAST = "google/gemini-2.5-flash"
    CAPABLE = "anthropic/claude-sonnet-4.5"


class EmbeddingModel(StrEnum):
    DEFAULT = "openai/text-embedding-3-small"


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: str

    def parsed_arguments(self, as_type: type[BaseModelT]) -> BaseModelT:
        return as_type.model_validate_json(self.arguments)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None


class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: type[BaseModel]


class TextDelta(BaseModel):
    text: str


class ToolCallDelta(BaseModel):
    """One or more tool calls the model has finished requesting (accumulated
    internally across streaming fragments - see below - and yielded once
    complete, not fragment-by-fragment)."""

    calls: list[ToolCall]


class StreamDone(BaseModel):
    """Terminal event. finish_reason distinguishes 'model produced a final
    text answer' from 'model wants tools then hasn't been given a chance to
    continue yet' - ChatService uses this to decide whether to loop."""

    finish_reason: Literal["stop", "tool_calls", "length"]


QueryEvent = TextDelta | ToolCallDelta | StreamDone


def build_client(api_key: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=_BASE_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=httpx.Timeout(10.0, read=60.0),
    )


def _serialize_message(message: ChatMessage) -> dict[str, object]:
    payload: dict[str, object] = {"role": message.role, "content": message.content}
    if message.tool_calls is not None:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in message.tool_calls
        ]
    if message.tool_call_id is not None:
        payload["tool_call_id"] = message.tool_call_id
    return payload


def _serialize_tools(tools: list[ToolDefinition]) -> list[dict[str, object]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters.model_json_schema(),
            },
        }
        for tool in tools
    ]


class _ToolCallBuffer(BaseModel):
    id: str = ""
    name: str = ""
    arguments_buffer: str = ""


async def query(
    client: httpx.AsyncClient,
    model: LLMModel,
    messages: list[ChatMessage],
    tools: list[ToolDefinition] | None = None,
) -> AsyncIterator[QueryEvent]:
    """MVP-NFR-3: stream a chat completion from OpenRouter.

    Yields TextDelta events as text arrives, then a ToolCallDelta (if the
    model requested tool calls) followed by a terminal StreamDone. Callers
    that want the full text can join the yielded TextDelta.text values
    themselves.
    """
    request_body: dict[str, object] = {
        "model": model.value,
        "messages": [_serialize_message(m) for m in messages],
        "stream": True,
    }
    if tools:
        request_body["tools"] = _serialize_tools(tools)
        request_body["tool_choice"] = "auto"

    async with client.stream("POST", "/chat/completions", json=request_body) as resp:
        resp.raise_for_status()

        # Tool-call argument fragments arrive split across many SSE chunks:
        # the first fragment at a given `index` carries `id`/`function.name`,
        # and every fragment at that index (including the first) carries a
        # piece of `function.arguments` that must be concatenated in order
        # before the buffered string is valid JSON. Nothing is yielded until
        # the terminal chunk (`finish_reason` set), since a partial buffer
        # can't be parsed as a complete ToolCall yet.
        pending_calls: dict[int, _ToolCallBuffer] = {}

        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            payload = line.removeprefix("data: ")
            if payload == "[DONE]":
                break
            chunk = json.loads(payload)
            choice = chunk["choices"][0]
            delta = choice["delta"]

            content = delta.get("content")
            if content:
                yield TextDelta(text=content)

            for fragment in delta.get("tool_calls") or []:
                index = fragment["index"]
                buffer = pending_calls.setdefault(index, _ToolCallBuffer())
                if "id" in fragment:
                    buffer.id = fragment["id"]
                function = fragment.get("function") or {}
                if "name" in function:
                    buffer.name = function["name"]
                if "arguments" in function:
                    buffer.arguments_buffer += function["arguments"]

            finish_reason = choice.get("finish_reason")
            if finish_reason is not None:
                if pending_calls:
                    yield ToolCallDelta(
                        calls=[
                            ToolCall(
                                id=buffer.id,
                                name=buffer.name,
                                arguments=buffer.arguments_buffer,
                            )
                            for buffer in pending_calls.values()
                        ]
                    )
                yield StreamDone(finish_reason=finish_reason)
                # OpenRouter may send further trailing chunks (e.g. a
                # usage-only chunk) after the terminal one; once this turn's
                # finish_reason has been observed and yielded, ignore the
                # rest rather than re-yielding a stale ToolCallDelta/StreamDone.
                return
