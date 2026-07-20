"""JiraTool (chat.md's Tools section). Wraps jira_client's two-step email->account-id
lookup + assigned-issues fetch; retries once after a silent refresh on a 401 per
oauth-integration.md's JIRA silent-refresh design before surfacing ToolExecutionError.
"""

from uuid import UUID

import httpx
from pydantic import BaseModel, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.integrations import jira_client
from app.repositories import activity_item_repo
from app.schemas.chat import ActivityItem, ActivityKind
from app.services import token_store
from app.services.chat_errors import ToolExecutionError
from app.services.tools.base import ActivityTool


class JiraToolParams(BaseModel):
    """Exactly one of jira_account_email/account_id must be given - email for the
    roster's 3 seeded members, account_id for anyone the model learned about via
    pre-fetch's assignable-users discovery instead (chat.md's Tools section; discovery
    frequently can't resolve an email at all - JIRA returns a blank emailAddress for
    most non-owner accounts, confirmed live against the real instance).
    """

    jira_account_email: str | None = None
    account_id: str | None = None
    project_key: str

    @model_validator(mode="after")
    def _exactly_one_identifier(self) -> "JiraToolParams":
        if bool(self.jira_account_email) == bool(self.account_id):
            raise ValueError("Exactly one of jira_account_email or account_id must be set")
        return self


class JiraTool(ActivityTool):
    name = "get_jira_tickets"
    description = (
        "Fetch a team member's assigned JIRA tickets (key, summary, status, priority, "
        "type, last updated, plus recent comments) for a given project. Use the "
        "project key from the pre-fetched top projects list. Identify the person by "
        "jira_account_email if they're on the roster, or by account_id if they were "
        "discovered via the pre-fetched project members list instead."
    )
    Params = JiraToolParams

    async def execute(
        self,
        session: AsyncSession,
        conversation_id: UUID,
        params: BaseModel,
        **credentials: str,
    ) -> list[ActivityItem]:
        """credentials must carry: team_member_id (UUID, as str), access_token,
        refresh_token, cloud_id, site_url (team_members.jira_site_url - the real
        browse-URL host, distinct from cloud_id which only builds the API base URL),
        jira_oauth_client_id, jira_oauth_client_secret - all resolved by the caller
        (ChatService/pre-fetch) from Key Vault/team_members/Settings, never fetched by
        this tool itself.
        """
        assert isinstance(params, JiraToolParams)
        team_member_id = UUID(credentials["team_member_id"])
        access_token = credentials["access_token"]
        refresh_token = credentials["refresh_token"]
        cloud_id = credentials["cloud_id"]
        site_url = credentials["site_url"]
        client_id = credentials["jira_oauth_client_id"]
        client_secret = credentials["jira_oauth_client_secret"]
        lookback_days = get_settings().activity_lookback_days

        try:
            issues = await self._fetch(access_token, cloud_id, params, lookback_days)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 401:
                raise ToolExecutionError(f"JIRA lookup failed: {exc}") from exc
            # Silent refresh, retry once - oauth-integration.md's JIRA silent-refresh
            # design. A second 401 after a successful refresh, or the refresh call
            # itself failing, both become a hard ToolExecutionError - no second retry.
            async with httpx.AsyncClient(timeout=10.0) as refresh_client:
                try:
                    refreshed = await jira_client.refresh_access_token(
                        refresh_client, refresh_token, client_id, client_secret
                    )
                except httpx.HTTPStatusError as refresh_exc:
                    raise ToolExecutionError(
                        f"JIRA re-authentication failed: {refresh_exc}"
                    ) from refresh_exc
            access_token = refreshed["access_token"]
            await token_store.store_jira_tokens(
                team_member_id, access_token, refreshed["refresh_token"]
            )
            try:
                issues = await self._fetch(access_token, cloud_id, params, lookback_days)
            except httpx.HTTPStatusError as retry_exc:
                raise ToolExecutionError(f"JIRA lookup failed: {retry_exc}") from retry_exc

        results: list[ActivityItem] = []
        client = jira_client.build_client(access_token, cloud_id)
        async with client:
            for issue in issues:
                # Priority/issue type folded into the pill label as enrichment text,
                # not a schema change - ActivityItem stays the narrow citable shape
                # (chat.md); richer descriptive fields don't need their own pill.
                label_bits = [issue.key]
                if issue.issue_type:
                    label_bits.append(issue.issue_type)
                if issue.priority:
                    label_bits.append(issue.priority)
                row = await activity_item_repo.upsert(
                    session,
                    conversation_id=conversation_id,
                    kind=ActivityKind.JIRA_TICKET.value,
                    external_id=issue.key,
                    label=" · ".join(label_bits),
                    url=f"{site_url.rstrip('/')}/browse/{issue.key}",
                )
                results.append(
                    ActivityItem(
                        id=row.id, kind=ActivityKind.JIRA_TICKET, label=row.label, url=row.url
                    )
                )

                try:
                    comments = await jira_client.get_comments(client, issue.key)
                except httpx.HTTPStatusError as exc:
                    raise ToolExecutionError(
                        f"JIRA comment lookup failed for {issue.key}: {exc}"
                    ) from exc
                for comment in comments:
                    snippet = comment.body_text[:80]
                    comment_row = await activity_item_repo.upsert(
                        session,
                        conversation_id=conversation_id,
                        kind=ActivityKind.JIRA_COMMENT.value,
                        external_id=comment.id,
                        label=f"Comment on {issue.key}: {snippet}",
                        url=f"{site_url.rstrip('/')}/browse/{issue.key}?focusedCommentId={comment.id}",
                    )
                    results.append(
                        ActivityItem(
                            id=comment_row.id,
                            kind=ActivityKind.JIRA_COMMENT,
                            label=comment_row.label,
                            url=comment_row.url,
                        )
                    )
        return results

    @staticmethod
    async def _fetch(
        access_token: str, cloud_id: str, params: JiraToolParams, lookback_days: int
    ) -> list[jira_client.JiraIssue]:
        client = jira_client.build_client(access_token, cloud_id)
        async with client:
            if params.account_id is not None:
                account_id = params.account_id
            else:
                assert params.jira_account_email is not None
                resolved = await jira_client.find_account_id_by_email(
                    client, params.jira_account_email
                )
                if resolved is None:
                    # Not a tool failure per chat.md - the model says so in its own prose.
                    return []
                account_id = resolved
            return await jira_client.get_issues_assigned_to(
                client, params.project_key, account_id, since_days=lookback_days
            )
