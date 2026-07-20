import httpx
import pytest
from pydantic import BaseModel

from app.config import get_settings
from app.services.llm_router import (
    ChatMessage,
    LLMModel,
    StreamDone,
    TextDelta,
    ToolCallDelta,
    ToolDefinition,
    build_client,
    query,
)


async def test_query_streams_nonempty_response() -> None:
    settings = get_settings()
    client = build_client(settings.openrouter_api_key)
    events = []
    async with client:
        async for event in query(
            client,
            LLMModel.FAST,
            [ChatMessage(role="user", content="Reply with the single word: hello")],
        ):
            events.append(event)

    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert text.strip()
    assert isinstance(events[-1], StreamDone)
    assert events[-1].finish_reason == "stop"


async def test_query_unauthorized_raises_http_status_error() -> None:
    client = build_client("sk-or-invalid-token")
    async with client:
        with pytest.raises(httpx.HTTPStatusError):
            async for _ in query(
                client,
                LLMModel.FAST,
                [ChatMessage(role="user", content="hi")],
            ):
                pass


class _WeatherParams(BaseModel):
    city: str


async def test_query_with_tools_yields_tool_call_delta() -> None:
    settings = get_settings()
    client = build_client(settings.openrouter_api_key)
    events = []
    async with client:
        async for event in query(
            client,
            LLMModel.FAST,
            [
                ChatMessage(
                    role="user",
                    content="Call the weather tool for the city of Boston.",
                )
            ],
            tools=[
                ToolDefinition(
                    name="get_weather",
                    description="Get the current weather for a city.",
                    parameters=_WeatherParams,
                )
            ],
        ):
            events.append(event)

    assert isinstance(events[-1], StreamDone)
    assert events[-1].finish_reason == "tool_calls"

    tool_call_deltas = [e for e in events if isinstance(e, ToolCallDelta)]
    assert len(tool_call_deltas) == 1
    calls = tool_call_deltas[0].calls
    assert len(calls) == 1
    assert calls[0].name == "get_weather"

    parsed = calls[0].parsed_arguments(_WeatherParams)
    assert "boston" in parsed.city.lower()
