"""GithubTool (chat.md's Tools section). Wraps github_client's commits/PRs fetch. No
refresh logic - GitHub OAuth App tokens don't expire under normal operation
(oauth-integration.md); a 401 here means real revocation, surfaced as ToolExecutionError.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.integrations import github_client
from app.repositories import activity_item_repo
from app.schemas.chat import ActivityItem, ActivityKind
from app.services.chat_errors import ToolExecutionError
from app.services.tools.base import ActivityTool


class GithubToolParams(BaseModel):
    github_login: str
    repo: str


def _review_decision(reviews: list[github_client.GithubReview]) -> str | None:
    """Reduces a PR's review list to one overall decision, using each reviewer's most
    recent review only (a reviewer can review multiple times) - GitHub's own merge-
    readiness semantics: any outstanding CHANGES_REQUESTED blocks, regardless of how
    many APPROVED reviews also exist.
    """
    latest_by_reviewer: dict[str, tuple[datetime, str]] = {}
    for review in reviews:
        if review.author_login is None or review.submitted_at is None:
            continue
        existing = latest_by_reviewer.get(review.author_login)
        if existing is None or review.submitted_at > existing[0]:
            latest_by_reviewer[review.author_login] = (review.submitted_at, review.state)
    states = {state for _, state in latest_by_reviewer.values()}
    if "CHANGES_REQUESTED" in states:
        return "CHANGES_REQUESTED"
    if "APPROVED" in states:
        return "APPROVED"
    if states:
        return "REVIEW_PENDING"
    return None


class GithubTool(ActivityTool):
    name = "get_github_activity"
    description = (
        "Fetch a team member's recent GitHub commits and pull requests (including "
        "review status and comments) for a given repo. Use the repo full_name from "
        "the pre-fetched top repos list, and the person's github_login from the "
        "roster or the pre-fetched contributors list."
    )
    Params = GithubToolParams

    async def execute(
        self,
        session: AsyncSession,
        conversation_id: UUID,
        params: BaseModel,
        **credentials: str,
    ) -> list[ActivityItem]:
        """credentials must carry: access_token - resolved by the caller from Key
        Vault, never fetched by this tool itself.
        """
        assert isinstance(params, GithubToolParams)
        access_token = credentials["access_token"]
        lookback_days = get_settings().activity_lookback_days
        since = datetime.now(UTC) - timedelta(days=lookback_days)

        client = github_client.build_client(access_token)
        try:
            async with client:
                commits = await github_client.get_recent_commits_by_author(
                    client, params.repo, params.github_login, since=since
                )
                pull_requests = await github_client.get_pull_requests_by_author(
                    client, params.repo, params.github_login
                )

                results: list[ActivityItem] = []
                for commit in commits:
                    row = await activity_item_repo.upsert(
                        session,
                        conversation_id=conversation_id,
                        kind=ActivityKind.GITHUB_COMMIT.value,
                        external_id=commit.sha,
                        label=commit.sha[:7],
                        url=commit.url,
                    )
                    results.append(
                        ActivityItem(
                            id=row.id,
                            kind=ActivityKind.GITHUB_COMMIT,
                            label=row.label,
                            url=row.url,
                        )
                    )

                for pr in pull_requests:
                    reviews = await github_client.get_pr_reviews(client, params.repo, pr.number)
                    decision = _review_decision(reviews)
                    # Review decision folded into the pill label as enrichment text,
                    # not a schema change - same reasoning as JiraTool's priority/type.
                    label = f"PR #{pr.number}" + (f" · {decision}" if decision else "")
                    row = await activity_item_repo.upsert(
                        session,
                        conversation_id=conversation_id,
                        kind=ActivityKind.GITHUB_PR.value,
                        external_id=str(pr.number),
                        label=label,
                        url=pr.url,
                    )
                    results.append(
                        ActivityItem(
                            id=row.id, kind=ActivityKind.GITHUB_PR, label=row.label, url=row.url
                        )
                    )

                    comments = await github_client.get_issue_comments(
                        client, params.repo, pr.number
                    )
                    for comment in comments:
                        snippet = comment.body[:80]
                        comment_row = await activity_item_repo.upsert(
                            session,
                            conversation_id=conversation_id,
                            kind=ActivityKind.GITHUB_COMMENT.value,
                            external_id=str(comment.id),  # int id -> str, matches upsert's key type
                            label=f"Comment on PR #{pr.number}: {snippet}",
                            url=f"{pr.url}#issuecomment-{comment.id}",
                        )
                        results.append(
                            ActivityItem(
                                id=comment_row.id,
                                kind=ActivityKind.GITHUB_COMMENT,
                                label=comment_row.label,
                                url=comment_row.url,
                            )
                        )
        except httpx.HTTPStatusError as exc:
            raise ToolExecutionError(f"GitHub lookup failed: {exc}") from exc

        return results
