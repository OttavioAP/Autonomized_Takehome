"""JIRA Cloud REST API v3 client (MVP-FR-9). Framework-agnostic: plain functions
taking an httpx.AsyncClient, no FastAPI imports, no config lookups of its own.
"""

from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel


class JiraIssue(BaseModel):
    key: str
    summary: str
    status: str
    assignee_account_id: str | None
    updated: datetime
    priority: str | None = None
    issue_type: str | None = None


class JiraComment(BaseModel):
    id: str
    issue_key: str
    author_display_name: str | None
    # Comment bodies are Atlassian Document Format (nested JSON), not plain text - callers
    # get a best-effort plain-text extraction (see _extract_plain_text below), not the raw ADF.
    body_text: str
    created: datetime


class JiraProject(BaseModel):
    key: str
    name: str


class JiraAssignableUser(BaseModel):
    account_id: str
    display_name: str
    email: str | None


def build_client(access_token: str, cloud_id: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=f"https://api.atlassian.com/ex/jira/{cloud_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10.0,
    )


def _parse_issue(raw: dict[str, Any]) -> JiraIssue:
    fields = raw["fields"]
    assignee = fields.get("assignee")
    priority = fields.get("priority")
    issue_type = fields.get("issuetype")
    return JiraIssue(
        key=raw["key"],
        summary=fields["summary"],
        status=fields["status"]["name"],
        assignee_account_id=assignee["accountId"] if assignee else None,
        updated=fields["updated"],
        priority=priority["name"] if priority else None,
        issue_type=issue_type["name"] if issue_type else None,
    )


async def get_issues_assigned_to(
    client: httpx.AsyncClient, project_key: str, account_id: str, since_days: int | None = None
) -> list[JiraIssue]:
    """MVP-FR-9: assigned issues plus status and recent updates for a user.

    since_days, when given, adds an `updated >= -Nd` JQL bound (Settings.
    activity_lookback_days at the caller) - chat.md's known gap for "what's X been up to
    this week"-style queries, closed here rather than left for the model to eyeball dates.
    """
    jql = f'project={project_key} AND assignee="{account_id}"'
    if since_days is not None:
        jql += f" AND updated >= -{since_days}d"
    jql += " ORDER BY updated DESC"
    resp = await client.get(
        "/rest/api/3/search/jql",
        params={"jql": jql, "fields": "summary,status,assignee,updated,priority,issuetype"},
    )
    resp.raise_for_status()
    return [_parse_issue(issue) for issue in resp.json()["issues"]]


async def find_account_id_by_email(client: httpx.AsyncClient, email: str) -> str | None:
    resp = await client.get("/rest/api/3/user/search", params={"query": email})
    resp.raise_for_status()
    results = resp.json()
    return results[0]["accountId"] if results else None


async def get_current_user_account_id(client: httpx.AsyncClient) -> str:
    """The account_id the given Bearer token actually authenticates as - resolved via
    /rest/api/3/myself, the same real endpoint utils/jira_seed_data.py already calls
    (over Basic auth) to resolve each demo account's accountId. Used at connect time
    so team_members.jira_account_id reflects whichever Atlassian account actually
    authorized, not whatever email was seeded - per oauth-integration.md, a team
    member can link any Atlassian account by connecting it, the same way GitHub's
    connect flow works.
    """
    resp = await client.get("/rest/api/3/myself")
    resp.raise_for_status()
    account_id: str = resp.json()["accountId"]
    return account_id


def _extract_plain_text(adf_body: dict[str, Any]) -> str:
    """Best-effort plain-text extraction from Atlassian Document Format - walks
    content nodes, joining text leaves with the block structure collapsed. ADF is a
    rich nested doc format (headings, lists, mentions, etc.); this project only needs
    a readable snippet for the model to read/cite, not a faithful re-render.
    """
    parts: list[str] = []

    def _walk(node: dict[str, Any]) -> None:
        if node.get("type") == "text":
            parts.append(node.get("text", ""))
        for child in node.get("content") or []:
            _walk(child)
        if node.get("type") in ("paragraph", "heading"):
            parts.append("\n")

    _walk(adf_body)
    return "".join(parts).strip()


def _parse_comment(raw: dict[str, Any], issue_key: str) -> JiraComment:
    author = raw.get("author")
    return JiraComment(
        id=raw["id"],
        issue_key=issue_key,
        author_display_name=author["displayName"] if author else None,
        body_text=_extract_plain_text(raw["body"]),
        created=raw["created"],
    )


async def get_comments(client: httpx.AsyncClient, issue_key: str) -> list[JiraComment]:
    """Comment thread on a single issue - richer "what's recently happened" signal than
    the bare `updated` timestamp/status change alone.
    """
    resp = await client.get(f"/rest/api/3/issue/{issue_key}/comment")
    resp.raise_for_status()
    return [_parse_comment(c, issue_key) for c in resp.json()["comments"]]


async def search_projects(client: httpx.AsyncClient) -> list[JiraProject]:
    """Every project the caller's token can browse - pre-fetch's "top projects"
    discovery (oauth-integration.md's Scope discovery section). No relevance ranking
    (JIRA has no "my projects" endpoint) - see chat.md for why this beats deriving a
    ranked list from the asking user's own issues (the person being asked about may not
    be the person asking, so ranking by the asker's own activity would be the wrong bias).
    """
    resp = await client.get("/rest/api/3/project/search", params={"maxResults": 50})
    resp.raise_for_status()
    return [JiraProject(key=p["key"], name=p["name"]) for p in resp.json()["values"]]


async def search_assignable_users(
    client: httpx.AsyncClient, project_key: str
) -> list[JiraAssignableUser]:
    """Real project members (assignable users), not just the app's static team_members
    roster - lets the model discover/reference people outside the 3 seeded accounts.
    emailAddress often comes back blank for accounts other than the token's own owner
    (confirmed live against the real instance) - account_id, not email, is the
    reliable identifier discovery hands back.
    """
    resp = await client.get("/rest/api/3/user/assignable/search", params={"project": project_key})
    resp.raise_for_status()
    return [
        JiraAssignableUser(
            account_id=u["accountId"],
            display_name=u["displayName"],
            email=u.get("emailAddress") or None,
        )
        for u in resp.json()
    ]


async def refresh_access_token(
    client: httpx.AsyncClient, refresh_token: str, client_id: str, client_secret: str
) -> dict[str, Any]:
    """Exchanges a refresh token for a new access token. Atlassian rotates the refresh
    token on every use - the caller MUST persist the new refresh_token from the response,
    not just the new access_token, or the next refresh will fail with a stale token.
    """
    resp = await client.post(
        "https://auth.atlassian.com/oauth/token",
        json={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        },
    )
    resp.raise_for_status()
    return resp.json()
