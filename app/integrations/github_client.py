"""GitHub REST API client (MVP-FR-10). Framework-agnostic: plain functions
taking an httpx.AsyncClient, no FastAPI imports, no config lookups of its own.
"""

from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel


class GithubCommit(BaseModel):
    sha: str
    message: str
    author_login: str | None
    date: datetime
    url: str


class GithubPullRequest(BaseModel):
    number: int
    title: str
    state: str
    author_login: str
    created_at: datetime
    url: str


def build_client(token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="https://api.github.com",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=10.0,
    )


def _parse_commit(raw: dict[str, Any]) -> GithubCommit:
    author = raw.get("author")
    return GithubCommit(
        sha=raw["sha"],
        message=raw["commit"]["message"],
        author_login=author["login"] if author else None,
        date=raw["commit"]["author"]["date"],
        url=raw["html_url"],
    )


def _parse_pull_request(raw: dict[str, Any]) -> GithubPullRequest:
    return GithubPullRequest(
        number=raw["number"],
        title=raw["title"],
        state=raw["state"],
        author_login=raw["user"]["login"],
        created_at=raw["created_at"],
        url=raw["html_url"],
    )


async def get_recent_commits_by_author(
    client: httpx.AsyncClient, repo: str, github_login: str, per_page: int = 20
) -> list[GithubCommit]:
    """MVP-FR-10: recent commits by a user in the demo repo."""
    resp = await client.get(
        f"/repos/{repo}/commits", params={"author": github_login, "per_page": per_page}
    )
    if resp.status_code == 409:
        # empty repository - no commits at all yet
        return []
    resp.raise_for_status()
    return [_parse_commit(c) for c in resp.json()]


async def get_pull_requests_by_author(
    client: httpx.AsyncClient, repo: str, github_login: str, state: str = "all"
) -> list[GithubPullRequest]:
    """MVP-FR-10: active/recent pull requests authored by a user."""
    resp = await client.get(f"/repos/{repo}/pulls", params={"state": state, "per_page": 20})
    resp.raise_for_status()
    return [_parse_pull_request(pr) for pr in resp.json() if pr["user"]["login"] == github_login]


async def get_repos_contributed_to(client: httpx.AsyncClient, github_login: str) -> list[str]:
    """MVP-FR-10: repositories the user has contributed to recently."""
    resp = await client.get(f"/users/{github_login}/repos", params={"per_page": 20})
    resp.raise_for_status()
    return [repo["full_name"] for repo in resp.json()]
