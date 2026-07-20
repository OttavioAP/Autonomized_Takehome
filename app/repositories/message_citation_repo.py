import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.message_citation import MessageCitation


async def create(
    session: AsyncSession, message_id: uuid.UUID, activity_item_id: uuid.UUID, ordinal: int
) -> MessageCitation:
    """Caller commits. ordinal is model-authoritative (chat.md's citation-ordinal
    decision) - passed in as-is, not recomputed here.
    """
    citation = MessageCitation(
        message_id=message_id, activity_item_id=activity_item_id, ordinal=ordinal
    )
    session.add(citation)
    await session.flush()
    return citation


async def get_by_id(session: AsyncSession, citation_id: uuid.UUID) -> MessageCitation | None:
    return await session.get(MessageCitation, citation_id)


async def list_for_message(session: AsyncSession, message_id: uuid.UUID) -> list[MessageCitation]:
    """Ordinal-ordered, matching sentinel order within the message's content."""
    result = await session.execute(
        select(MessageCitation)
        .where(MessageCitation.message_id == message_id)
        .order_by(MessageCitation.ordinal)
    )
    return list(result.scalars())


async def delete(session: AsyncSession, citation_id: uuid.UUID) -> None:
    """Basic CRUD completeness — nothing in chat.md's design calls this yet."""
    citation = await session.get(MessageCitation, citation_id)
    if citation is None:
        raise ValueError(f"No message_citations row for id={citation_id}")
    await session.delete(citation)
