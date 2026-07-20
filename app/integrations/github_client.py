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
    review_decision: str | None = None


class GithubReview(BaseModel):
    id: int
    author_login: str | None
    state: str
    submitted_at: datetime | None


class GithubComment(BaseModel):
    id: int
    issue_number: int
    author_login: str | None
    body: str
    created_at: datetime


class GithubRepo(BaseModel):
    full_name: str
    description: str | None


class GithubContributor(BaseModel):
    login: str
    contributions: int


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
        # Not present on the list-PRs payload - filled in by GithubTool from a separate
        # get_pr_reviews() call, kept optional here so this parser stays a pure mapping
        # of what /pulls actually returns.
        review_decision=None,
    )


async def get_recent_commits_by_author(
    client: httpx.AsyncClient,
    repo: str,
    github_login: str,
    per_page: int = 20,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[GithubCommit]:
    """MVP-FR-10: recent commits by a user in the demo repo. since/until (ISO 8601,
    GitHub's own native commits-endpoint params - confirmed live, not derived
    client-side) let a caller scope to e.g. "this week" directly rather than eyeballing
    dates in whatever the default page returns - chat.md's previously-known gap.
    """
    params: dict[str, Any] = {"author": github_login, "per_page": per_page}
    if since is not None:
        params["since"] = since.isoformat()
    if until is not None:
        params["until"] = until.isoformat()
    resp = await client.get(f"/repos/{repo}/commits", params=params)
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


async def get_pr_reviews(
    client: httpx.AsyncClient, repo: str, pr_number: int
) -> list[GithubReview]:
    """Review state on a single PR - enrichment for GithubTool's PR results, richer
    than the bare open/closed `state` field alone.
    """
    resp = await client.get(f"/repos/{repo}/pulls/{pr_number}/reviews")
    resp.raise_for_status()
    reviews: list[GithubReview] = []
    for raw in resp.json():
        user = raw.get("user")
        reviews.append(
            GithubReview(
                id=raw["id"],
                author_login=user["login"] if user else None,
                state=raw["state"],
                submitted_at=raw.get("submitted_at"),
            )
        )
    return reviews


async def get_issue_comments(
    client: httpx.AsyncClient, repo: str, issue_number: int
) -> list[GithubComment]:
    """Comment thread on an issue/PR (GitHub PRs are issues under the hood, same
    endpoint serves both) - richer "what's recently happened" signal than commit/PR
    metadata alone, same role JIRA's get_comments plays.
    """
    resp = await client.get(f"/repos/{repo}/issues/{issue_number}/comments")
    resp.raise_for_status()
    comments: list[GithubComment] = []
    for raw in resp.json():
        user = raw.get("user")
        comments.append(
            GithubComment(
                id=raw["id"],
                issue_number=issue_number,
                author_login=user["login"] if user else None,
                body=raw["body"],
                created_at=raw["created_at"],
            )
        )
    return comments


async def get_user_repos(client: httpx.AsyncClient, per_page: int = 10) -> list[GithubRepo]:
    """The authenticated caller's own repos, most-recently-pushed first - pre-fetch's
    "top repos" discovery (oauth-integration.md's Scope discovery section). Uses
    /user/repos (the token's own repos), not /users/{login}/repos (a public listing
    for an arbitrary login) - the two are different endpoints with different auth
    semantics; this one reflects private-repo access the token actually has.
    """
    resp = await client.get(
        "/user/repos", params={"sort": "pushed", "direction": "desc", "per_page": per_page}
    )
    resp.raise_for_status()
    return [
        GithubRepo(full_name=repo["full_name"], description=repo.get("description"))
        for repo in resp.json()
    ]


async def get_repo_contributors(
    client: httpx.AsyncClient, repo: str, per_page: int = 10
) -> list[GithubContributor]:
    """Real contributors to a repo, not just the app's static team_members roster -
    lets the model discover/reference GitHub logins outside the 3 seeded accounts.
    Server-aggregated and sorted by contribution count - no client-side dedup needed.
    """
    resp = await client.get(f"/repos/{repo}/contributors", params={"per_page": per_page})
    resp.raise_for_status()
    return [
        GithubContributor(login=c["login"], contributions=c["contributions"]) for c in resp.json()
    ]
