from httpx import AsyncClient


async def test_index_renders_ping_button(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert "Ping the server" in response.text


async def test_ping_returns_pong_fragment(client: AsyncClient) -> None:
    response = await client.get("/ping")
    assert response.status_code == 200
    assert "pong" in response.text
