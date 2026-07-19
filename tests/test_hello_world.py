from httpx import AsyncClient


async def test_index_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/", follow_redirects=False, headers={"accept": "text/html"})
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


async def test_index_renders_ping_button(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.get("/")
    assert response.status_code == 200
    assert "Ping the server" in response.text


async def test_ping_returns_pong_fragment(client: AsyncClient) -> None:
    response = await client.get("/ping")
    assert response.status_code == 200
    assert "pong" in response.text
