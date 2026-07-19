import httpx
import pytest

from app.config import get_settings
from app.services.llm_router import ChatMessage, LLMModel, build_client, query


async def test_query_streams_nonempty_response() -> None:
    settings = get_settings()
    client = build_client(settings.openrouter_api_key)
    chunks = []
    async with client:
        async for chunk in query(
            client,
            LLMModel.FAST,
            [ChatMessage(role="user", content="Reply with the single word: hello")],
        ):
            chunks.append(chunk)

    assert chunks
    assert "".join(chunks).strip()


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
