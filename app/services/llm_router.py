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
from typing import Literal

import httpx
from pydantic import BaseModel

_BASE_URL = "https://openrouter.ai/api/v1"


class LLMModel(StrEnum):
    FAST = "google/gemini-2.5-flash"
    CAPABLE = "anthropic/claude-sonnet-4.5"


class EmbeddingModel(StrEnum):
    DEFAULT = "openai/text-embedding-3-small"


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


def build_client(api_key: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=_BASE_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=httpx.Timeout(10.0, read=60.0),
    )


async def query(
    client: httpx.AsyncClient, model: LLMModel, messages: list[ChatMessage]
) -> AsyncIterator[str]:
    """MVP-NFR-3: stream a chat completion from OpenRouter.

    Yields text deltas as they arrive. Callers that want the full response
    can join the yielded chunks themselves.
    """
    async with client.stream(
        "POST",
        "/chat/completions",
        json={
            "model": model.value,
            "messages": [m.model_dump() for m in messages],
            "stream": True,
        },
    ) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            payload = line.removeprefix("data: ")
            if payload == "[DONE]":
                break
            chunk = json.loads(payload)
            delta = chunk["choices"][0]["delta"].get("content")
            if delta:
                yield delta
