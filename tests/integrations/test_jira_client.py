import json
import os
from pathlib import Path

import httpx
import pytest

from app.integrations.jira_client import (
    build_client,
    find_account_id_by_email,
    get_comments,
    get_issues_assigned_to,
    refresh_access_token,
    search_assignable_users,
    search_projects,
)

# No real JIRA OAuth access token can be obtained in this environment: build_client's new
# signature needs a Bearer access_token + cloud_id from a live, interactive Atlassian
# consent-screen authorize-code exchange, and JIRA_OAUTH_CLIENT_ID is still unset in .env
# (the app registration itself hasn't happened yet). Once a real OAuth connect exists,
# set JIRA_TEST_ACCESS_TOKEN / JIRA_TEST_CLOUD_ID / JIRA_TEST_PROJECT_KEY /
# JIRA_TEST_ACCOUNT_EMAIL to unskip these.
_ACCESS_TOKEN = os.environ.get("JIRA_TEST_ACCESS_TOKEN")
_CLOUD_ID = os.environ.get("JIRA_TEST_CLOUD_ID")
_PROJECT_KEY = os.environ.get("JIRA_TEST_PROJECT_KEY")
_ACCOUNT_EMAIL = os.environ.get("JIRA_TEST_ACCOUNT_EMAIL")

_skip_no_live_token = pytest.mark.skip(
    reason="No real JIRA OAuth access token available - requires a live, interactive "
    "Atlassian consent-screen authorize-code exchange, which can't be scripted in this "
    "sandboxed session. Blocked on app/api/oauth.py's connect flow existing and a human "
    "completing it once (see implementation_log.md)."
)

# --- Basic-auth (API token) live tests for the discovery/comments/enrichment functions
# added alongside Phase 3/5 work. These verify the endpoint shapes/parsing logic
# directly against the real autonomizedtest1.atlassian.net instance - unblocked, unlike
# the Bearer/cloud_id-scoped tests above, because JIRA API tokens (utils/
# jira_connect_check.py's existing pattern) work over Basic auth against the direct
# site base URL, which is exempt from the OAuth rework for standalone/manual use
# (oauth-integration.md's Client rework section). This does NOT exercise
# build_client's real Bearer/cloud_id path - the underlying REST endpoints/response
# shapes are auth-mechanism-agnostic (confirmed live during this session), but full
# verification of the Bearer-auth path itself is still blocked on the same real 3LO
# token gap as the tests above.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_JIRA_SITE_BASE_URL = "https://autonomizedtest1.atlassian.net"
_JIRA_KAN_PROJECT_KEY = "KAN"


def _load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def _basic_auth_client() -> httpx.AsyncClient:
    env = _load_env(REPO_ROOT / ".env")
    email = (
        os.environ.get("Autonomized_Test_1_Protonmail_Email")
        or env["Autonomized_Test_1_Protonmail_Email"]
    )
    api_token = (
        os.environ.get("Autonomized_Test_1_Jira_API_Key") or env["Autonomized_Test_1_Jira_API_Key"]
    )
    return httpx.AsyncClient(base_url=_JIRA_SITE_BASE_URL, auth=(email, api_token), timeout=10.0)


async def test_search_projects_returns_real_project() -> None:
    async with _basic_auth_client() as client:
        projects = await search_projects(client)

    assert any(p.key == _JIRA_KAN_PROJECT_KEY for p in projects)


async def test_search_assignable_users_returns_real_users() -> None:
    async with _basic_auth_client() as client:
        users = await search_assignable_users(client, _JIRA_KAN_PROJECT_KEY)

    assert len(users) > 0
    assert all(u.account_id for u in users)


async def test_get_comments_on_issue_with_no_comments_returns_empty() -> None:
    async with _basic_auth_client() as client:
        comments = await get_comments(client, "KAN-8")

    assert comments == []


def test_build_client_sets_bearer_auth_header_and_cloud_scoped_base_url() -> None:
    client = build_client("fake-access-token", "fake-cloud-id")
    assert str(client.base_url) == "https://api.atlassian.com/ex/jira/fake-cloud-id/"
    assert client.headers["authorization"] == "Bearer fake-access-token"


async def test_refresh_access_token_sends_correct_request_shape() -> None:
    """Not a live Atlassian call - uses httpx's own MockTransport (part of httpx core,
    not an external mocking library, consistent with this project's no-mocking stance)
    to inspect the constructed request without hitting the network, and returns a
    canned response so the function's return value can also be verified.
    """
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            200,
            json={
                "access_token": "new-access-token",
                "refresh_token": "new-rotated-refresh-token",
                "expires_in": 3600,
                "scope": "read:jira-work read:jira-user offline_access",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await refresh_access_token(
            client,
            refresh_token="old-refresh-token",
            client_id="test-client-id",
            client_secret="test-client-secret",
        )

    request = captured["request"]
    assert str(request.url) == "https://auth.atlassian.com/oauth/token"
    assert request.method == "POST"
    body = json.loads(request.content)
    assert body == {
        "grant_type": "refresh_token",
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
        "refresh_token": "old-refresh-token",
    }
    assert result["access_token"] == "new-access-token"
    assert result["refresh_token"] == "new-rotated-refresh-token"


@_skip_no_live_token
async def test_get_issues_assigned_to_returns_seeded_issue() -> None:
    assert _CLOUD_ID and _PROJECT_KEY and _ACCOUNT_EMAIL
    client = build_client(_ACCESS_TOKEN or "", _CLOUD_ID)
    async with client:
        # John (Test_1) is seeded (utils/jira_seed_data.py) with "Deploy hello world to
        # Microsoft Azure", status Done.
        account_id = await find_account_id_by_email(client, _ACCOUNT_EMAIL)
        assert account_id is not None

        issues = await get_issues_assigned_to(client, _PROJECT_KEY, account_id)

    assert any(issue.summary == "Deploy hello world to Microsoft Azure" for issue in issues)
    seeded = next(i for i in issues if i.summary == "Deploy hello world to Microsoft Azure")
    assert seeded.status == "Done"
    assert seeded.assignee_account_id == account_id


@_skip_no_live_token
async def test_find_account_id_by_email_unknown_user_returns_none() -> None:
    assert _CLOUD_ID
    client = build_client(_ACCESS_TOKEN or "", _CLOUD_ID)
    async with client:
        account_id = await find_account_id_by_email(client, "nonexistent-user@example.com")

    assert account_id is None


@_skip_no_live_token
async def test_get_issues_assigned_to_unknown_account_returns_empty() -> None:
    assert _CLOUD_ID and _PROJECT_KEY
    client = build_client(_ACCESS_TOKEN or "", _CLOUD_ID)
    async with client:
        issues = await get_issues_assigned_to(
            client, _PROJECT_KEY, "000000:00000000-0000-0000-0000-000000000000"
        )

    assert issues == []
