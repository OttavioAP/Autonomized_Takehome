import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.team_member import TeamMember


async def get_by_azure_upn(session: AsyncSession, azure_upn: str) -> TeamMember | None:
    """Pre-fetch's and OAuth routes' login-time entry point: resolves the logged-in
    session's user_upn to the team_members row backing it. None if the Azure identity
    isn't a seeded team member.
    """
    result = await session.execute(select(TeamMember).where(TeamMember.azure_upn == azure_upn))
    return result.scalar_one_or_none()


async def list_all(session: AsyncSession) -> list[TeamMember]:
    """The full roster rendered into the chat system prompt."""
    result = await session.execute(select(TeamMember).order_by(TeamMember.display_name))
    return list(result.scalars())


async def set_jira_cloud_id(
    session: AsyncSession, team_member_id: uuid.UUID, cloud_id: str, site_url: str
) -> None:
    """Called once from GET /oauth/jira/callback after resolving both fields via one
    accessible-resources call - neither is a secret, safe to keep in Postgres (see
    oauth-integration.md's Token storage section). Caller commits.
    """
    team_member = await session.get(TeamMember, team_member_id)
    if team_member is None:
        raise ValueError(f"No team_members row for id={team_member_id}")
    team_member.jira_cloud_id = cloud_id
    team_member.jira_site_url = site_url


async def set_jira_account_id(
    session: AsyncSession, team_member_id: uuid.UUID, account_id: str
) -> None:
    """Called once from GET /oauth/jira/callback after resolving the connecting
    account's real account_id via /rest/api/3/myself - not a secret, safe to keep in
    Postgres. Supersedes jira_account_email as the identifier pre_fetch.py/the chat
    roster use once set, since a team member can connect any Atlassian account (not
    necessarily the one the seed email points at). Caller commits.
    """
    team_member = await session.get(TeamMember, team_member_id)
    if team_member is None:
        raise ValueError(f"No team_members row for id={team_member_id}")
    team_member.jira_account_id = account_id
