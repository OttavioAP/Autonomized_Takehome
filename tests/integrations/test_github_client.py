from app.config import get_settings
from app.integrations.github_client import (
    build_client,
    get_pull_requests_by_author,
    get_recent_commits_by_author,
)


async def test_get_recent_commits_by_author_returns_seeded_commit() -> None:
    settings = get_settings()
    client = build_client(settings.github_token)
    async with client:
        # John (Test_1, login "Autonomized1") is seeded (utils/github_seed_data.py)
        # with a "Deploy hello world to Microsoft Azure" commit on main.
        commits = await get_recent_commits_by_author(client, settings.github_repo, "Autonomized1")

    assert any(c.message == "Deploy hello world to Microsoft Azure" for c in commits)


async def test_get_recent_commits_by_author_unknown_user_returns_empty() -> None:
    settings = get_settings()
    client = build_client(settings.github_token)
    async with client:
        commits = await get_recent_commits_by_author(
            client, settings.github_repo, "nonexistent-user-xyz"
        )

    assert commits == []


async def test_get_pull_requests_by_author_returns_seeded_pr() -> None:
    settings = get_settings()
    client = build_client(settings.github_token)
    async with client:
        # Sarah (Test_2, login "autonomized2") is seeded with an open PR (#1) for the
        # "Bare-minimum integrations" branch.
        prs = await get_pull_requests_by_author(client, settings.github_repo, "autonomized2")

    titles = {pr.title for pr in prs}
    assert "Bare-minimum integrations: add connectivity check scripts" in titles


async def test_get_pull_requests_by_author_unknown_user_returns_empty() -> None:
    settings = get_settings()
    client = build_client(settings.github_token)
    async with client:
        prs = await get_pull_requests_by_author(
            client, settings.github_repo, "nonexistent-user-xyz"
        )

    assert prs == []
