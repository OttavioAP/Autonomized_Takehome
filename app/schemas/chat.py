"""Pydantic schemas for the chat feature (chat.md's Schemas section)."""

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class ActivityKind(StrEnum):
    JIRA_TICKET = "jira_ticket"
    JIRA_COMMENT = "jira_comment"
    JIRA_PROJECT = "jira_project"
    JIRA_PERSON = "jira_person"
    GITHUB_COMMIT = "github_commit"
    GITHUB_PR = "github_pr"
    GITHUB_COMMENT = "github_comment"
    GITHUB_REPO = "github_repo"
    GITHUB_USER = "github_user"


class ActivityItem(BaseModel):
    """Service-facing normalized shape both tools return. Feeds citation validation."""

    id: UUID
    kind: ActivityKind
    label: str
    url: str


class ActivityItemOut(BaseModel):
    """Page-render view - same fields as ActivityItem, named separately since the
    two may diverge (e.g. ActivityItemOut gaining render-only fields later)."""

    id: UUID
    kind: ActivityKind
    label: str
    url: str


class MessageOut(BaseModel):
    id: UUID
    role: Literal["user", "assistant", "system"]
    content: str  # raw, sentinels embedded - template resolves them at render
    citations: list[ActivityItemOut]  # pre-joined; list index + 1 == ordinal
    created_at: datetime


class ChatRequest(BaseModel):
    query: str
    csrf_token: str


# SSE event payloads. Each is the JSON `data:` body for its named SSE `event:`.
class ToolStatusEvent(BaseModel):
    message: str  # "Checking Sarah's JIRA tickets..." - ephemeral, never persisted


class TokenEvent(BaseModel):
    text: str


class CiteEvent(BaseModel):
    ordinal: int
    item: ActivityItemOut


class CiteErrorEvent(BaseModel):
    ordinal: int
    detail: str = "Couldn't resolve a citation the assistant made — this may be a bug."


class ErrorEvent(BaseModel):
    detail: str  # OpenRouter/transport failure - no model left to explain itself


class SSEEnvelope(BaseModel):
    """Typing convenience for the Python code building these - not a literal wire
    wrapper. The route still emits real `event: <name>\\ndata: <json>\\n\\n` SSE
    frames; `event` here just drives a single `emit()` dispatch helper."""

    event: Literal["tool-status", "token", "cite", "cite-error", "error"]
    data: ToolStatusEvent | TokenEvent | CiteEvent | CiteErrorEvent | ErrorEvent


# Pre-fetch/scope-discovery context (oauth-integration.md's Scope discovery section).
# `id` is populated once discover_scope() upserts the ref into activity_items
# (JIRA_PROJECT/JIRA_PERSON/GITHUB_REPO/GITHUB_USER - added once project/repo/person
# pills became citable, see chat_system_prompt.md) - None only if the caller ran
# discover_scope() without a session (no upsert happened, e.g. a context where
# citations don't apply). Still prompt context primarily; no tool accepts these
# directly as arguments except where noted.
class JiraProjectRef(BaseModel):
    id: UUID | None = None
    key: str
    name: str


class JiraPersonRef(BaseModel):
    """A real project member discovered via JIRA's assignable-users search, distinct
    from team_members' static 3-person roster. account_id (not email) is the reliable
    identifier - JIRA's own API returns a blank emailAddress for most accounts other
    than the token's own owner (confirmed live). JiraToolParams accepts account_id
    as an alternative to jira_account_email specifically so the model can act on a
    discovered person, not just roster members.
    """

    id: UUID | None = None
    account_id: str
    display_name: str
    email: str | None = None


class GithubRepoRef(BaseModel):
    id: UUID | None = None
    full_name: str
    description: str | None = None


class GithubCollaboratorRef(BaseModel):
    """Unlike JiraPersonRef, no tool needs a dedicated "collaborator identifier"
    parameter, since GithubToolParams.github_login already accepts any login
    directly, discovered or from the roster alike."""

    id: UUID | None = None
    login: str
    name: str | None = None
