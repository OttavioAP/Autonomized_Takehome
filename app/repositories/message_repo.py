import uuid
from datetime import UTC, datetime
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.activity_item import ActivityItem
from app.db.models.message import Message, MessageRole
from app.db.models.message_citation import MessageCitation
from app.schemas.chat import ActivityItemOut, ActivityKind, MessageOut


async def create(
    session: AsyncSession, conversation_id: uuid.UUID, role: MessageRole, content: str
) -> Message:
    """Caller commits. content carries citation sentinels embedded, not stripped."""
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        created_at=datetime.now(UTC),
    )
    session.add(message)
    await session.flush()
    return message


async def get_by_id(session: AsyncSession, message_id: uuid.UUID) -> Message | None:
    return await session.get(Message, message_id)


async def list_for_conversation(session: AsyncSession, conversation_id: uuid.UUID) -> list[Message]:
    """Oldest-first bare Message rows. list_out_for_conversation() below is the
    citations-pre-joined MessageOut view GET /conversations/{id} renders from.
    """
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return list(result.scalars())


async def list_out_for_conversation(
    session: AsyncSession, conversation_id: uuid.UUID
) -> list[MessageOut]:
    """MessageOut per chat.md's Repositories section: each message with its citations
    pre-joined, ordinal-ordered so list index + 1 == ordinal (the contract
    resolve_citations relies on). Used for history replay on GET /conversations/{id}.
    """
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    messages = list(result.scalars())

    out: list[MessageOut] = []
    for message in messages:
        citation_rows = await session.execute(
            select(ActivityItem)
            .join(MessageCitation, MessageCitation.activity_item_id == ActivityItem.id)
            .where(MessageCitation.message_id == message.id)
            .order_by(MessageCitation.ordinal)
        )
        citations = [
            ActivityItemOut(
                id=item.id, kind=ActivityKind(item.kind), label=item.label, url=item.url
            )
            for item in citation_rows.scalars()
        ]
        out.append(
            MessageOut(
                id=message.id,
                role=cast(Literal["user", "assistant", "system"], message.role.value),
                content=message.content,
                citations=citations,
                created_at=message.created_at,
            )
        )
    return out


async def delete(session: AsyncSession, message_id: uuid.UUID) -> None:
    """Basic CRUD completeness — nothing in chat.md's design calls this yet."""
    message = await session.get(Message, message_id)
    if message is None:
        raise ValueError(f"No messages row for id={message_id}")
    await session.delete(message)
