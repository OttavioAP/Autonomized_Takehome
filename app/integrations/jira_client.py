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


def build_client(base_url: str, email: str, api_token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url, auth=(email, api_token), timeout=10.0)


def _parse_issue(raw: dict[str, Any]) -> JiraIssue:
    fields = raw["fields"]
    assignee = fields.get("assignee")
    return JiraIssue(
        key=raw["key"],
        summary=fields["summary"],
        status=fields["status"]["name"],
        assignee_account_id=assignee["accountId"] if assignee else None,
        updated=fields["updated"],
    )


async def get_issues_assigned_to(
    client: httpx.AsyncClient, project_key: str, account_id: str
) -> list[JiraIssue]:
    """MVP-FR-9: assigned issues plus status and recent updates for a user."""
    jql = f'project={project_key} AND assignee="{account_id}" ORDER BY updated DESC'
    resp = await client.get(
        "/rest/api/3/search/jql",
        params={"jql": jql, "fields": "summary,status,assignee,updated"},
    )
    resp.raise_for_status()
    return [_parse_issue(issue) for issue in resp.json()["issues"]]


async def find_account_id_by_email(client: httpx.AsyncClient, email: str) -> str | None:
    resp = await client.get("/rest/api/3/user/search", params={"query": email})
    resp.raise_for_status()
    results = resp.json()
    return results[0]["accountId"] if results else None
