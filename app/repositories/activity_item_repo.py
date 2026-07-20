import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.activity_item import ActivityItem


async def create(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    kind: str,
    external_id: str,
    label: str,
    url: str,
) -> ActivityItem:
    """Caller commits. Plain insert - the upsert-by-(conversation_id, kind, external_id)
    behavior chat.md's Tools section describes (pre-fetch/tool-call paths sharing one
    upsert function) is later work; this is just the basic create.
    """
    item = ActivityItem(
        conversation_id=conversation_id,
        kind=kind,
        external_id=external_id,
        label=label,
        url=url,
        fetched_at=datetime.now(UTC),
    )
    session.add(item)
    await session.flush()
    return item


async def get_by_id(session: AsyncSession, activity_item_id: uuid.UUID) -> ActivityItem | None:
    return await session.get(ActivityItem, activity_item_id)


async def list_for_conversation(
    session: AsyncSession, conversation_id: uuid.UUID
) -> list[ActivityItem]:
    """A conversation's current item set - the citation-validation set per chat.md."""
    result = await session.execute(
        select(ActivityItem).where(ActivityItem.conversation_id == conversation_id)
    )
    return list(result.scalars())


async def get_by_natural_key(
    session: AsyncSession, conversation_id: uuid.UUID, kind: str, external_id: str
) -> ActivityItem | None:
    """Looks up by the table's own unique constraint - the key an upsert would check."""
    result = await session.execute(
        select(ActivityItem).where(
            ActivityItem.conversation_id == conversation_id,
            ActivityItem.kind == kind,
            ActivityItem.external_id == external_id,
        )
    )
    return result.scalar_one_or_none()


async def delete(session: AsyncSession, activity_item_id: uuid.UUID) -> None:
    """Basic CRUD completeness — nothing in chat.md's design calls this yet."""
    item = await session.get(ActivityItem, activity_item_id)
    if item is None:
        raise ValueError(f"No activity_items row for id={activity_item_id}")
    await session.delete(item)
