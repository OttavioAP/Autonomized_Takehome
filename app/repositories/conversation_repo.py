import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.conversation import Conversation


async def create(session: AsyncSession, team_member_id: uuid.UUID) -> Conversation:
    """New empty conversation (title=NULL, prefetched_at=NULL). Caller commits."""
    now = datetime.now(UTC)
    conversation = Conversation(team_member_id=team_member_id, created_at=now, updated_at=now)
    session.add(conversation)
    await session.flush()
    return conversation


async def get_by_id(session: AsyncSession, conversation_id: uuid.UUID) -> Conversation | None:
    return await session.get(Conversation, conversation_id)


async def list_for_team_member(
    session: AsyncSession, team_member_id: uuid.UUID
) -> list[Conversation]:
    """Most-recent-first, for the conversation-switcher list."""
    result = await session.execute(
        select(Conversation)
        .where(Conversation.team_member_id == team_member_id)
        .order_by(Conversation.updated_at.desc())
    )
    return list(result.scalars())


async def get_most_recent(session: AsyncSession, team_member_id: uuid.UUID) -> Conversation | None:
    """GET /'s redirect target. None if the user has no conversations yet."""
    result = await session.execute(
        select(Conversation)
        .where(Conversation.team_member_id == team_member_id)
        .order_by(Conversation.updated_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def update(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    *,
    title: str | None = None,
    prefetched_at: datetime | None = None,
) -> Conversation:
    """Bumps updated_at unconditionally; title/prefetched_at only when passed. Caller commits."""
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise ValueError(f"No conversations row for id={conversation_id}")
    if title is not None:
        conversation.title = title
    if prefetched_at is not None:
        conversation.prefetched_at = prefetched_at
    conversation.updated_at = datetime.now(UTC)
    return conversation


async def delete(session: AsyncSession, conversation_id: uuid.UUID) -> None:
    """Basic CRUD completeness — chat.md's Routes section doesn't currently expose a delete
    endpoint (see its 'Explicitly out of scope' list), so nothing calls this yet.
    """
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise ValueError(f"No conversations row for id={conversation_id}")
    await session.delete(conversation)
