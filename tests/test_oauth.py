"""Integration tests for app/api/oauth.py. The interactive authorize-code exchange with
a real consent screen can't be automated (per Phase 1's own gate description) - covered
instead by a manual browser round-trip. What's tested here: auth/CSRF/state enforcement,
the connect-page rendering both connected/not-connected states against the real Key
Vault, and the /auth/callback + GET / gate redirect logic - everything that doesn't
require a human clicking through Atlassian/GitHub's own UI.
"""

import re

from httpx import AsyncClient


async def test_jira_connect_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/oauth/jira/connect", follow_redirects=False)
    assert response.status_code == 401


async def test_github_connect_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/oauth/github/connect", follow_redirects=False)
    assert response.status_code == 401


async def test_connect_page_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/oauth/connect", follow_redirects=False)
    assert response.status_code == 401


async def test_jira_connect_redirects_to_atlassian_with_state_cookie(
    authenticated_client: AsyncClient,
) -> None:
    response = await authenticated_client.get("/oauth/jira/connect", follow_redirects=False)

    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("https://auth.atlassian.com/authorize")
    assert "response_type=code" in location
    assert "prompt=consent" in location
    assert "oauth_state" in response.cookies


async def test_github_connect_redirects_to_github_with_state_cookie(
    authenticated_client: AsyncClient,
) -> None:
    response = await authenticated_client.get("/oauth/github/connect", follow_redirects=False)

    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("https://github.com/login/oauth/authorize")
    assert "scope=repo" in location
    assert "oauth_state" in response.cookies


async def test_jira_callback_rejects_mismatched_state(authenticated_client: AsyncClient) -> None:
    authenticated_client.cookies.set("oauth_state", "expected-state")
    response = await authenticated_client.get(
        "/oauth/jira/callback", params={"code": "fake-code", "state": "wrong-state"}
    )
    assert response.status_code == 400


async def test_jira_callback_rejects_missing_state_cookie(
    authenticated_client: AsyncClient,
) -> None:
    response = await authenticated_client.get(
        "/oauth/jira/callback", params={"code": "fake-code", "state": "some-state"}
    )
    assert response.status_code == 400


async def test_github_callback_rejects_mismatched_state(
    authenticated_client: AsyncClient,
) -> None:
    authenticated_client.cookies.set("oauth_state", "expected-state")
    response = await authenticated_client.get(
        "/oauth/github/callback", params={"code": "fake-code", "state": "wrong-state"}
    )
    assert response.status_code == 400


async def test_disconnect_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/oauth/jira/disconnect")
    assert response.status_code == 401


async def test_disconnect_rejects_wrong_csrf_token(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.post(
        "/oauth/jira/disconnect", data={"csrf_token": "wrong-token"}
    )
    assert response.status_code == 403


async def test_connect_page_shows_connected_state(authenticated_client: AsyncClient) -> None:
    # authenticated_client's fixture already stores real (fake-valued) tokens for John -
    # this asserts the page reads that live Key Vault state correctly, not a fixture
    # implementation detail.
    response = await authenticated_client.get("/oauth/connect")
    assert response.status_code == 200
    assert response.text.count("Connected") >= 2  # both providers, plus not "Not connected"
    assert "Not connected" not in response.text


async def test_disconnect_then_connect_page_shows_not_connected(
    authenticated_client: AsyncClient,
) -> None:
    index_response = await authenticated_client.get("/oauth/connect")
    match = re.search(r'name="csrf_token" value="([^"]+)"', index_response.text)
    assert match is not None
    csrf_token = match.group(1)

    disconnect_response = await authenticated_client.post(
        "/oauth/jira/disconnect", data={"csrf_token": csrf_token}, follow_redirects=False
    )
    assert disconnect_response.status_code == 302
    assert disconnect_response.headers["location"] == "/oauth/connect"

    connect_page = await authenticated_client.get("/oauth/connect")
    assert "Not connected" in connect_page.text

    # GET / must now redirect to the gate rather than rendering, since JIRA is
    # disconnected - this is the actual enforcement, not just the connect page's display.
    index_after_disconnect = await authenticated_client.get("/", follow_redirects=False)
    assert index_after_disconnect.status_code == 302
    assert index_after_disconnect.headers["location"] == "/oauth/connect"


async def test_double_disconnect_is_idempotent(authenticated_client: AsyncClient) -> None:
    """token_store.delete_jira_tokens/delete_github_token are documented as no-op-safe on
    an already-disconnected user - exercise that through the real route, not just the
    service function directly (tests/integrations/test_token_store.py already covers the
    service layer in isolation).
    """
    index_response = await authenticated_client.get("/oauth/connect")
    match = re.search(r'name="csrf_token" value="([^"]+)"', index_response.text)
    assert match is not None
    csrf_token = match.group(1)

    first = await authenticated_client.post(
        "/oauth/github/disconnect", data={"csrf_token": csrf_token}, follow_redirects=False
    )
    second = await authenticated_client.post(
        "/oauth/github/disconnect", data={"csrf_token": csrf_token}, follow_redirects=False
    )
    assert first.status_code == 302
    assert second.status_code == 302
