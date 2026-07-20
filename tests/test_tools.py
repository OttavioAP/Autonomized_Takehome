"""Live integration tests for JiraTool/GithubTool (chat.md's Tools section, Phase 3's
own gate: exercise execute() against real APIs, not just the underlying client
functions tests/integrations/ already covers).
"""

import os
from pathlib import Path

import pytest

from app.db.session import db
from app.repositories import activity_item_repo, conversation_repo, team_member_repo
from app.schemas.chat import ActivityKind
from app.services.tools.github_tool import GithubTool, GithubToolParams
from app.services.tools.jira_tool import JiraTool, JiraToolParams

REPO_ROOT = Path(__file__).resolve().parent.parent
GITHUB_REPO = "Autonomized1/Autonomized_Test_Project_1"


def _load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def _github_token() -> str:
    # Same stand-in as tests/integrations/test_github_client.py's _github_token(): no
    # real per-user GitHub OAuth token exists in this sandboxed session, so the demo
    # account's fine-grained PAT is used as an opaque Bearer token instead.
    return (
        os.environ.get("Autonomized_Test_1_Github_PAT")
        or _load_env(REPO_ROOT / ".env")["Autonomized_Test_1_Github_PAT"]
    )


async def test_github_tool_execute_persists_real_activity_items() -> None:
    # Sarah (Test_2, login "autonomized2") is the seeded PR author (see
    # tests/integrations/test_github_client.py's own comment on this) - John
    # (Autonomized1) only has a seeded commit, no PR, so this exercises Sarah's
    # identity to cover both the commit and PR/review/comment upsert paths in one test.
    async for session in db.get_session():
        sarah = await team_member_repo.get_by_azure_upn(
            session, "sarah@ottavioantperuzzigmail.onmicrosoft.com"
        )
        assert sarah is not None
        conversation = await conversation_repo.create(session, sarah.id)
        await session.commit()

        results = await GithubTool().execute(
            session,
            conversation.id,
            GithubToolParams(github_login="autonomized2", repo=GITHUB_REPO),
            access_token=_github_token(),
        )
        await session.commit()

    assert any(item.kind == ActivityKind.GITHUB_PR for item in results)

    # Real persistence, not just the returned in-memory shape - re-fetch the whole
    # conversation's item set, the same query ChatService's citation validation uses.
    pr_item = next(item for item in results if item.kind == ActivityKind.GITHUB_PR)
    async for session in db.get_session():
        all_items = await activity_item_repo.list_for_conversation(session, conversation.id)
    assert any(item.id == pr_item.id for item in all_items)


async def test_github_tool_execute_unknown_user_returns_empty() -> None:
    async for session in db.get_session():
        john = await team_member_repo.get_by_azure_upn(
            session, "john@ottavioantperuzzigmail.onmicrosoft.com"
        )
        assert john is not None
        conversation = await conversation_repo.create(session, john.id)
        await session.commit()

        results = await GithubTool().execute(
            session,
            conversation.id,
            GithubToolParams(github_login="nonexistent-user-xyz", repo=GITHUB_REPO),
            access_token=_github_token(),
        )
        await session.commit()

    assert results == []


# --- JiraTool.execute() ---------------------------------------------------------
# Same real gap as tests/integrations/test_jira_client.py's skipped live tests: no real
# JIRA 3LO OAuth access_token/cloud_id exists yet - JiraTool.execute() calls
# jira_client.build_client(access_token, cloud_id), which is Bearer-auth against
# api.atlassian.com/ex/jira/{cloud_id}, a genuinely different auth mechanism/base URL
# from the Basic-auth API-token tests in tests/integrations/test_jira_client.py (those
# verify the endpoint/parsing logic live, but not this Bearer/cloud_id-scoped path).
# Self-unskips via the same JIRA_TEST_* env vars once a human completes a real
# /oauth/jira/connect browser round-trip and captures the resulting token/cloud_id.
_ACCESS_TOKEN = os.environ.get("JIRA_TEST_ACCESS_TOKEN")
_CLOUD_ID = os.environ.get("JIRA_TEST_CLOUD_ID")
_PROJECT_KEY = os.environ.get("JIRA_TEST_PROJECT_KEY")
_ACCOUNT_EMAIL = os.environ.get("JIRA_TEST_ACCOUNT_EMAIL")
_SITE_URL = os.environ.get("JIRA_TEST_SITE_URL")

_skip_no_live_token = pytest.mark.skip(
    reason="No real JIRA OAuth access token available - requires a live, interactive "
    "Atlassian consent-screen authorize-code exchange. Set JIRA_TEST_ACCESS_TOKEN / "
    "JIRA_TEST_CLOUD_ID / JIRA_TEST_PROJECT_KEY / JIRA_TEST_ACCOUNT_EMAIL / "
    "JIRA_TEST_SITE_URL to unskip."
)


@_skip_no_live_token
async def test_jira_tool_execute_persists_real_activity_items() -> None:
    assert _CLOUD_ID and _PROJECT_KEY and _ACCOUNT_EMAIL and _SITE_URL
    async for session in db.get_session():
        john = await team_member_repo.get_by_azure_upn(
            session, "john@ottavioantperuzzigmail.onmicrosoft.com"
        )
        assert john is not None
        conversation = await conversation_repo.create(session, john.id)
        await session.commit()

        results = await JiraTool().execute(
            session,
            conversation.id,
            JiraToolParams(jira_account_email=_ACCOUNT_EMAIL, project_key=_PROJECT_KEY),
            team_member_id=str(john.id),
            access_token=_ACCESS_TOKEN or "",
            refresh_token="",
            cloud_id=_CLOUD_ID,
            site_url=_SITE_URL,
            jira_oauth_client_id="",
            jira_oauth_client_secret="",
        )
        await session.commit()

    assert any(item.kind == ActivityKind.JIRA_TICKET for item in results)
