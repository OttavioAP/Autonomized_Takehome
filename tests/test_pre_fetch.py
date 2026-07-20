"""Live integration tests for pre_fetch.run() (chat.md's Pre-fetch section). Phase 3's
own stated gate: run it twice against the same conversation_id, confirm the second run
is a no-op (activity_items row count doesn't change).
"""

import os
from pathlib import Path

import pytest

from app.db.session import db
from app.repositories import activity_item_repo, conversation_repo, team_member_repo
from app.services import pre_fetch, token_store

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
    return (
        os.environ.get("Autonomized_Test_1_Github_PAT")
        or _load_env(REPO_ROOT / ".env")["Autonomized_Test_1_Github_PAT"]
    )


async def test_run_twice_is_cached_second_time_a_no_op() -> None:
    """GitHub-only path: no real JIRA 3LO token exists in this session (same gap as
    tests/test_tools.py's skipped JiraTool test), so team_member.jira_cloud_id stays
    unset here and pre_fetch.run()'s JIRA leg is a no-op both times by construction -
    this still fully exercises the GitHub discovery/activity leg plus the caching gate
    itself (conversations.prefetched_at), which is provider-agnostic logic.
    """
    async for session in db.get_session():
        john = await team_member_repo.get_by_azure_upn(
            session, "john@ottavioantperuzzigmail.onmicrosoft.com"
        )
        assert john is not None
        conversation = await conversation_repo.create(session, john.id)
        await session.commit()
    assert john is not None

    await token_store.store_github_token(john.id, _github_token())
    try:
        async for session in db.get_session():
            scope_1 = await pre_fetch.run(session, conversation.id, john)
            await session.commit()

        async for session in db.get_session():
            items_after_first_run = await activity_item_repo.list_for_conversation(
                session, conversation.id
            )

        assert len(items_after_first_run) > 0
        assert len(scope_1.github_repos) > 0
        assert any(r.full_name == GITHUB_REPO for r in scope_1.github_repos)

        async for session in db.get_session():
            refreshed_conversation = await conversation_repo.get_by_id(session, conversation.id)
            assert refreshed_conversation is not None
            assert refreshed_conversation.prefetched_at is not None

        # Second run: a real caller (the route) is expected to check prefetched_at
        # IS NULL before calling run() at all (chat.md's explicit gate) - this test
        # calls run() directly a second time to prove the underlying upsert path is
        # itself idempotent (same activity_items row count), which is what actually
        # backs that caching guarantee regardless of which layer checks the flag.
        async for session in db.get_session():
            await pre_fetch.run(session, conversation.id, john)
            await session.commit()

        async for session in db.get_session():
            items_after_second_run = await activity_item_repo.list_for_conversation(
                session, conversation.id
            )

        assert len(items_after_second_run) == len(items_after_first_run)
    finally:
        await token_store.delete_github_token(john.id)


# --- JIRA leg of discovery/pre-fetch ---------------------------------------------
# Same real gap as tests/test_tools.py's skipped JiraTool test: no real JIRA 3LO
# access_token/cloud_id exists in this session.
_ACCESS_TOKEN = os.environ.get("JIRA_TEST_ACCESS_TOKEN")
_CLOUD_ID = os.environ.get("JIRA_TEST_CLOUD_ID")
_SITE_URL = os.environ.get("JIRA_TEST_SITE_URL")

_skip_no_live_token = pytest.mark.skip(
    reason="No real JIRA OAuth access token available. Set JIRA_TEST_ACCESS_TOKEN / "
    "JIRA_TEST_CLOUD_ID / JIRA_TEST_SITE_URL to unskip."
)


@_skip_no_live_token
async def test_run_discovers_real_jira_projects_and_people() -> None:
    assert _CLOUD_ID and _SITE_URL
    async for session in db.get_session():
        john = await team_member_repo.get_by_azure_upn(
            session, "john@ottavioantperuzzigmail.onmicrosoft.com"
        )
        assert john is not None
        john.jira_cloud_id = _CLOUD_ID
        john.jira_site_url = _SITE_URL
        conversation = await conversation_repo.create(session, john.id)
        await session.commit()
    assert john is not None

    await token_store.store_jira_tokens(john.id, _ACCESS_TOKEN or "", "")
    try:
        async for session in db.get_session():
            scope = await pre_fetch.run(session, conversation.id, john)
            await session.commit()

        assert len(scope.jira_projects) > 0
        assert len(scope.jira_people) > 0
    finally:
        await token_store.delete_jira_tokens(john.id)
