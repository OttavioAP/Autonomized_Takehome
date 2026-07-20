import os
from pathlib import Path

from app.integrations.github_client import (
    build_client,
    get_issue_comments,
    get_pr_reviews,
    get_pull_requests_by_author,
    get_recent_commits_by_author,
    get_repo_contributors,
    get_user_repos,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REPO = "Autonomized1/Autonomized_Test_Project_1"


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
    # TRANSITIONAL: build_client(token: str) itself is fully OAuth-ready (an opaque Bearer
    # token, no knowledge of where it came from) - but no real per-user GitHub OAuth token
    # exists yet (app/api/oauth.py's connect flow isn't built), so this test stands in with
    # the seed/connect-check demo account's fine-grained PAT as a Bearer token, read directly
    # from .env (same pattern utils/github_connect_check.py uses; not a real Settings field -
    # OAuth tokens are per-user, resolved from Key Vault at request time). A PAT and an OAuth
    # access token are both just opaque Bearer strings here, so these assertions stay
    # meaningful, but this is the pre-OAuth demo credential the rework exists to move away
    # from - swap this for a real per-user OAuth token once a connect flow exists, same as
    # test_jira_client.py's skipped live tests are waiting to do.
    return (
        os.environ.get("Autonomized_Test_1_Github_PAT")
        or _load_env(REPO_ROOT / ".env")["Autonomized_Test_1_Github_PAT"]
    )


async def test_get_recent_commits_by_author_returns_seeded_commit() -> None:
    client = build_client(_github_token())
    async with client:
        # John (Test_1, login "Autonomized1") is seeded (utils/github_seed_data.py)
        # with a "Deploy hello world to Microsoft Azure" commit on main.
        commits = await get_recent_commits_by_author(client, REPO, "Autonomized1")

    assert any(c.message == "Deploy hello world to Microsoft Azure" for c in commits)


async def test_get_recent_commits_by_author_unknown_user_returns_empty() -> None:
    client = build_client(_github_token())
    async with client:
        commits = await get_recent_commits_by_author(client, REPO, "nonexistent-user-xyz")

    assert commits == []


async def test_get_pull_requests_by_author_returns_seeded_pr() -> None:
    client = build_client(_github_token())
    async with client:
        # Sarah (Test_2, login "autonomized2") is seeded with an open PR (#1) for the
        # "Bare-minimum integrations" branch.
        prs = await get_pull_requests_by_author(client, REPO, "autonomized2")

    titles = {pr.title for pr in prs}
    assert "Bare-minimum integrations: add connectivity check scripts" in titles


async def test_get_pull_requests_by_author_unknown_user_returns_empty() -> None:
    client = build_client(_github_token())
    async with client:
        prs = await get_pull_requests_by_author(client, REPO, "nonexistent-user-xyz")

    assert prs == []


async def test_get_user_repos_returns_seeded_repo() -> None:
    client = build_client(_github_token())
    async with client:
        repos = await get_user_repos(client)

    assert any(r.full_name == REPO for r in repos)


async def test_get_repo_contributors_returns_seeded_contributor() -> None:
    client = build_client(_github_token())
    async with client:
        contributors = await get_repo_contributors(client, REPO)

    assert any(c.login == "Autonomized1" for c in contributors)


async def test_get_pr_reviews_on_pr_with_no_reviews_returns_empty() -> None:
    client = build_client(_github_token())
    async with client:
        reviews = await get_pr_reviews(client, REPO, 1)

    assert reviews == []


async def test_get_issue_comments_on_pr_with_no_comments_returns_empty() -> None:
    client = build_client(_github_token())
    async with client:
        comments = await get_issue_comments(client, REPO, 1)

    assert comments == []
