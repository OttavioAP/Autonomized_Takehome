import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.message import Message, MessageRole


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
    """Oldest-first, matching turn order. Returns bare Message rows, not the
    citations-pre-joined MessageOut shape chat.md's Repositories section describes —
    that join depends on app/schemas/chat.py, which doesn't exist yet.
    """
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return list(result.scalars())


async def delete(session: AsyncSession, message_id: uuid.UUID) -> None:
    """Basic CRUD completeness — nothing in chat.md's design calls this yet."""
    message = await session.get(Message, message_id)
    if message is None:
        raise ValueError(f"No messages row for id={message_id}")
    await session.delete(message)
