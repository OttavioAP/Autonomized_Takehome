import uuid

from app.services.token_store import (
    delete_github_token,
    delete_jira_tokens,
    get_github_token,
    get_jira_tokens,
    store_github_token,
    store_jira_tokens,
)


async def test_store_and_get_jira_tokens_round_trips() -> None:
    team_member_id = uuid.uuid4()
    await store_jira_tokens(team_member_id, "access-123", "refresh-456")

    tokens = await get_jira_tokens(team_member_id)

    assert tokens is not None
    assert tokens.access_token == "access-123"
    assert tokens.refresh_token == "refresh-456"

    await delete_jira_tokens(team_member_id)


async def test_store_and_get_github_token_round_trips() -> None:
    team_member_id = uuid.uuid4()
    await store_github_token(team_member_id, "gh-token-789")

    token = await get_github_token(team_member_id)

    assert token == "gh-token-789"

    await delete_github_token(team_member_id)


async def test_get_jira_tokens_never_stored_returns_none() -> None:
    assert await get_jira_tokens(uuid.uuid4()) is None


async def test_get_github_token_never_stored_returns_none() -> None:
    assert await get_github_token(uuid.uuid4()) is None


async def test_delete_jira_tokens_then_get_returns_none() -> None:
    team_member_id = uuid.uuid4()
    await store_jira_tokens(team_member_id, "access-123", "refresh-456")

    await delete_jira_tokens(team_member_id)

    assert await get_jira_tokens(team_member_id) is None


async def test_delete_jira_tokens_twice_does_not_raise() -> None:
    team_member_id = uuid.uuid4()
    await store_jira_tokens(team_member_id, "access-123", "refresh-456")

    await delete_jira_tokens(team_member_id)
    await delete_jira_tokens(team_member_id)


async def test_delete_github_token_twice_does_not_raise() -> None:
    team_member_id = uuid.uuid4()
    await store_github_token(team_member_id, "gh-token-789")

    await delete_github_token(team_member_id)
    await delete_github_token(team_member_id)
