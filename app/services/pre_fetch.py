"""Deterministic, no-LLM pre-fetch (chat.md's "Pre-fetch, cached per conversation"
section): at first render of a conversation, fetch the logged-in user's own JIRA/GitHub
activity via the same tools/upsert path tool-calling uses, and discover the scope (top
projects/repos/people) that becomes system-prompt context for Phase 5's ChatService
(oauth-integration.md's Scope discovery section).

Resolves the design gap flagged in this module's earlier draft: JiraTool/GithubTool
still need a concrete project_key/repo per call, but that value is no longer a
caller-supplied argument - it comes from discover_scope() below, run live against the
user's own JIRA/GitHub token. The single top project/repo (by discovery's own
ordering) is what pre-fetch uses for "my tickets"/"my commits"; the full discovered
lists (up to Settings.discovery_top_n each) are returned for the system prompt to
render, so the model can reach for a *different* project/repo/person than pre-fetch's
own pick when the question is about someone else.
"""

from datetime import UTC, datetime
from uuid import UUID

import httpx
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models.team_member import TeamMember
from app.integrations import github_client, jira_client
from app.repositories import activity_item_repo, conversation_repo
from app.schemas.chat import (
    ActivityKind,
    GithubCollaboratorRef,
    GithubRepoRef,
    JiraPersonRef,
    JiraProjectRef,
)
from app.services import token_store
from app.services.chat_errors import ToolExecutionError
from app.services.tools.github_tool import GithubTool, GithubToolParams
from app.services.tools.jira_tool import JiraTool, JiraToolParams


class DiscoveredScope(BaseModel):
    """Scope-discovery results, rendered into the chat system prompt (chat.md's Prompts
    section) alongside the team roster. Prompt context only - no ActivityItem/citation
    involvement.
    """

    jira_projects: list[JiraProjectRef] = []
    jira_people: list[JiraPersonRef] = []
    github_repos: list[GithubRepoRef] = []
    github_collaborators: list[GithubCollaboratorRef] = []


async def discover_scope(
    jira_client_instance: httpx.AsyncClient | None,
    github_client_instance: httpx.AsyncClient | None,
    *,
    session: AsyncSession | None = None,
    conversation_id: UUID | None = None,
    jira_site_url: str | None = None,
) -> DiscoveredScope:
    """Runs JIRA/GitHub scope discovery independently per provider - either client may
    be None (provider not connected, or its own discovery call failed) without
    blocking the other. Collaborators are discovered only from the single
    most-recently-pushed repo (not fanned out across all discovered repos) - this is
    prompt-context-only data, so one extra call is a better tradeoff than
    discovery_top_n extra calls for a completeness gain the model rarely needs.

    When session/conversation_id are given, each discovered project/person/repo/
    collaborator is also upserted into activity_items (JIRA_PROJECT/JIRA_PERSON/
    GITHUB_REPO/GITHUB_USER) via the same shared upsert() every other ActivityItem
    goes through, and the returned refs carry a real `id` the model can cite -
    matching chat.md's "the model cites, it does not construct" trust boundary
    instead of leaving these as prompt-only text with no clickable link. jira_site_url
    is required alongside session/conversation_id for the JIRA half, since a JIRA
    project/person deep-link needs the real site host (jira_client's Bearer/cloud_id
    client only knows the API host - the same cloud_id-vs-site_url distinction
    JiraTool already has to account for). Omit all three to skip upserting entirely
    (prompt-context-only refs with id=None) - e.g. a caller with no citation context.
    """
    settings = get_settings()
    scope = DiscoveredScope()
    can_upsert_jira = session is not None and conversation_id is not None and jira_site_url
    can_upsert_github = session is not None and conversation_id is not None

    if jira_client_instance is not None:
        try:
            projects = await jira_client.search_projects(jira_client_instance)
            scope.jira_projects = [
                JiraProjectRef(key=p.key, name=p.name) for p in projects[: settings.discovery_top_n]
            ]
            if can_upsert_jira:
                assert session is not None and conversation_id is not None and jira_site_url
                for project in scope.jira_projects:
                    row = await activity_item_repo.upsert(
                        session,
                        conversation_id=conversation_id,
                        kind=ActivityKind.JIRA_PROJECT.value,
                        external_id=project.key,
                        label=f"{project.key}: {project.name}",
                        url=f"{jira_site_url.rstrip('/')}/jira/software/projects/{project.key}/boards",
                    )
                    project.id = row.id

            if scope.jira_projects:
                users = await jira_client.search_assignable_users(
                    jira_client_instance, scope.jira_projects[0].key
                )
                scope.jira_people = [
                    JiraPersonRef(
                        account_id=u.account_id, display_name=u.display_name, email=u.email
                    )
                    for u in users[: settings.discovery_top_n]
                ]
                if can_upsert_jira:
                    assert session is not None and conversation_id is not None and jira_site_url
                    for person in scope.jira_people:
                        row = await activity_item_repo.upsert(
                            session,
                            conversation_id=conversation_id,
                            kind=ActivityKind.JIRA_PERSON.value,
                            external_id=person.account_id,
                            label=person.display_name,
                            url=f"{jira_site_url.rstrip('/')}/jira/people/{person.account_id}",
                        )
                        person.id = row.id
        except httpx.HTTPError:
            # Best-effort discovery (same reasoning as the activity pre-fetch below) -
            # covers both a real error status and connection-level unreachability.
            pass

    if github_client_instance is not None:
        try:
            repos = await github_client.get_user_repos(
                github_client_instance, per_page=settings.discovery_top_n
            )
            scope.github_repos = [
                GithubRepoRef(full_name=r.full_name, description=r.description) for r in repos
            ]
            if can_upsert_github:
                assert session is not None and conversation_id is not None
                for repo in scope.github_repos:
                    row = await activity_item_repo.upsert(
                        session,
                        conversation_id=conversation_id,
                        kind=ActivityKind.GITHUB_REPO.value,
                        external_id=repo.full_name,
                        label=repo.full_name,
                        url=f"https://github.com/{repo.full_name}",
                    )
                    repo.id = row.id

            if scope.github_repos:
                contributors = await github_client.get_repo_contributors(
                    github_client_instance,
                    scope.github_repos[0].full_name,
                    per_page=settings.discovery_top_n,
                )
                scope.github_collaborators = [
                    GithubCollaboratorRef(login=c.login) for c in contributors
                ]
                if can_upsert_github:
                    assert session is not None and conversation_id is not None
                    for collaborator in scope.github_collaborators:
                        row = await activity_item_repo.upsert(
                            session,
                            conversation_id=conversation_id,
                            kind=ActivityKind.GITHUB_USER.value,
                            external_id=collaborator.login,
                            label=collaborator.login,
                            url=f"https://github.com/{collaborator.login}",
                        )
                        collaborator.id = row.id
        except httpx.HTTPError:
            pass

    return scope


async def run(
    session: AsyncSession, conversation_id: UUID, team_member: TeamMember
) -> DiscoveredScope:
    """Fetches the user's own JIRA tickets/GitHub activity (scoped to the top
    discovered project/repo) and runs scope discovery, upserting activity into
    activity_items and returning the discovered scope for the system prompt. Caller
    commits (same transaction as the route that triggered this, per spec).

    Errors from either provider are swallowed into a best-effort partial pre-fetch
    (unlike tool-calling's ToolExecutionError, which propagates to the model) - pre-fetch
    runs at page-render time with no chat turn in progress to feed an error back into,
    and a user whose JIRA pre-fetch fails shouldn't be unable to load the page at all.
    """
    settings = get_settings()
    scope = DiscoveredScope()

    jira_tokens = await token_store.get_jira_tokens(team_member.id)
    if jira_tokens is not None and team_member.jira_cloud_id and team_member.jira_site_url:
        jira_http_client = jira_client.build_client(
            jira_tokens.access_token, team_member.jira_cloud_id
        )
        async with jira_http_client:
            discovered = await discover_scope(
                jira_http_client,
                None,
                session=session,
                conversation_id=conversation_id,
                jira_site_url=team_member.jira_site_url,
            )
            scope.jira_projects = discovered.jira_projects
            scope.jira_people = discovered.jira_people

        if scope.jira_projects:
            # jira_account_id (resolved at connect time - see app/api/oauth.py's
            # jira_callback) is preferred once set: it's the account that actually
            # authorized, which may not be the one jira_account_email (a seed-time
            # default) points at. Falls back to email for a user who hasn't
            # reconnected since this field was introduced.
            identity_kwargs = (
                {"account_id": team_member.jira_account_id}
                if team_member.jira_account_id
                else {"jira_account_email": team_member.jira_account_email}
            )
            try:
                await JiraTool().execute(
                    session,
                    conversation_id,
                    JiraToolParams(
                        project_key=scope.jira_projects[0].key,
                        **identity_kwargs,
                    ),
                    team_member_id=str(team_member.id),
                    access_token=jira_tokens.access_token,
                    refresh_token=jira_tokens.refresh_token,
                    cloud_id=team_member.jira_cloud_id,
                    site_url=team_member.jira_site_url,
                    jira_oauth_client_id=settings.jira_oauth_client_id,
                    jira_oauth_client_secret=settings.jira_oauth_client_secret,
                )
            except ToolExecutionError:
                pass  # Best-effort pre-fetch - see docstring.

    github_token = await token_store.get_github_token(team_member.id)
    if github_token is not None:
        github_http_client = github_client.build_client(github_token)
        async with github_http_client:
            discovered = await discover_scope(
                None, github_http_client, session=session, conversation_id=conversation_id
            )
            scope.github_repos = discovered.github_repos
            scope.github_collaborators = discovered.github_collaborators

        if scope.github_repos:
            try:
                await GithubTool().execute(
                    session,
                    conversation_id,
                    GithubToolParams(
                        github_login=team_member.github_login,
                        repo=scope.github_repos[0].full_name,
                    ),
                    access_token=github_token,
                )
            except ToolExecutionError:
                pass

    await conversation_repo.update(session, conversation_id, prefetched_at=datetime.now(UTC))
    return scope
