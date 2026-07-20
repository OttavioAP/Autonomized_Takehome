from httpx import AsyncClient


async def test_index_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/", follow_redirects=False, headers={"accept": "text/html"})
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


async def test_index_redirects_authenticated_user_into_a_conversation(
    authenticated_client: AsyncClient,
) -> None:
    # GET / no longer renders index.html directly (chat.md's Routes change) - it
    # redirects into the user's most recent conversation view, creating one if needed.
    redirect = await authenticated_client.get("/", follow_redirects=False)
    assert redirect.status_code == 302
    assert redirect.headers["location"].startswith("/conversations/")

    page = await authenticated_client.get("/", follow_redirects=True)
    assert page.status_code == 200
    assert 'id="chat-form"' in page.text


async def test_ping_returns_pong_fragment(client: AsyncClient) -> None:
    response = await client.get("/ping")
    assert response.status_code == 200
    assert "pong" in response.text
