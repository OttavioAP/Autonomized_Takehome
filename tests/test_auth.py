import re

import httpx
from httpx import AsyncClient

from app.auth import oidc
from app.config import get_settings


async def test_login_redirects_to_azure_authorize_endpoint(client: AsyncClient) -> None:
    response = await client.get("/auth/login", follow_redirects=False)
    settings = get_settings()

    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith(
        f"https://login.microsoftonline.com/{settings.azure_tenant_id}/oauth2/v2.0/authorize"
    )
    assert f"client_id={settings.azure_client_id}" in location
    assert "oauth_state" in response.cookies


async def test_login_authorize_url_is_reachable_on_azure() -> None:
    """Regression test: catches path-construction bugs (e.g. a duplicated /v2.0/
    segment) that self-referential assertions against our own generated URL can't
    catch, by hitting the real Microsoft endpoint and requiring a non-404 response.
    """
    settings = get_settings()
    url = oidc.build_authorize_url(
        tenant_id=settings.azure_tenant_id,
        client_id=settings.azure_client_id,
        redirect_uri=settings.azure_redirect_uri,
        state="test-state",
    )
    async with httpx.AsyncClient() as client:
        response = await client.get(url, follow_redirects=False)

    assert response.status_code != 404


async def test_callback_rejects_mismatched_state(client: AsyncClient) -> None:
    client.cookies.set("oauth_state", "expected-state")
    response = await client.get(
        "/auth/callback", params={"code": "fake-code", "state": "wrong-state"}
    )
    assert response.status_code == 400


async def test_callback_rejects_missing_state_cookie(client: AsyncClient) -> None:
    response = await client.get(
        "/auth/callback", params={"code": "fake-code", "state": "some-state"}
    )
    assert response.status_code == 400


async def test_logout_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/auth/logout")
    assert response.status_code == 401


async def test_logout_rejects_wrong_csrf_token(authenticated_client: AsyncClient) -> None:
    response = await authenticated_client.post("/auth/logout", data={"csrf_token": "wrong-token"})
    assert response.status_code == 403


async def test_logout_revokes_session_and_clears_cookie(authenticated_client: AsyncClient) -> None:
    # Read the real csrf_token back out via a rendered page's hidden form field
    # rather than reaching into the fixture's internals, so this exercises the
    # actual value a browser would submit. GET / now redirects into the user's
    # conversation view (chat.md's Routes change), so follow the redirect to reach
    # the page that actually renders the sign-out form.
    index_response = await authenticated_client.get("/", follow_redirects=True)
    assert 'name="csrf_token"' in index_response.text

    match = re.search(r'name="csrf_token" value="([^"]+)"', index_response.text)
    assert match is not None
    csrf_token = match.group(1)

    response = await authenticated_client.post(
        "/auth/logout", data={"csrf_token": csrf_token}, follow_redirects=False
    )
    assert response.status_code == 302

    # Session cookie should be cleared/rejected on the next request
    followup = await authenticated_client.get(
        "/", follow_redirects=False, headers={"accept": "text/html"}
    )
    assert followup.status_code == 302
    assert followup.headers["location"] == "/login"
