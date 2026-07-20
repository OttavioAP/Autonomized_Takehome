import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
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


async def upsert(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    kind: str,
    external_id: str,
    label: str,
    url: str,
) -> ActivityItem:
    """The one function chat.md's Tools/Pre-fetch sections both call - "cite the same
    ticket in turn 3 that was fetched in turn 1" resolving to a stable id depends on
    this being the single upsert path both callers share, keyed on the table's own
    unique constraint (conversation_id, kind, external_id). Refreshes label/url/
    fetched_at on an existing row (a ticket's title can change between fetches) rather
    than leaving stale display text pointing at the same stable id. Caller commits.

    Uses a real atomic INSERT ... ON CONFLICT DO UPDATE, not a check-then-insert
    (get_by_natural_key then create) - the latter has a TOCTOU race between two
    concurrent writers targeting the same natural key (a real, reachable case once
    ChatService started running same-round tool calls concurrently, each against its
    own session/transaction - two upserts for the same (conversation_id, kind,
    external_id) can both see "not found" before either commits, then both attempt an
    INSERT, and the second hits the unique constraint). Postgres's ON CONFLICT clause
    makes the check-and-write one atomic statement instead.
    """
    now = datetime.now(UTC)
    stmt = (
        pg_insert(ActivityItem)
        .values(
            conversation_id=conversation_id,
            kind=kind,
            external_id=external_id,
            label=label,
            url=url,
            fetched_at=now,
        )
        .on_conflict_do_update(
            index_elements=["conversation_id", "kind", "external_id"],
            set_={"label": label, "url": url, "fetched_at": now},
        )
        .returning(ActivityItem)
    )
    result = await session.execute(stmt)
    await session.flush()
    row_id = result.scalar_one().id
    # Re-fetch through the session identity map so the caller gets a fully-attached
    # ORM instance (the RETURNING row from a Core insert() isn't session-tracked the
    # same way an ORM-constructed object is).
    item = await session.get(ActivityItem, row_id)
    assert item is not None, f"just-upserted activity_items row {row_id} vanished"
    return item


async def delete(session: AsyncSession, activity_item_id: uuid.UUID) -> None:
    """Basic CRUD completeness — nothing in chat.md's design calls this yet."""
    item = await session.get(ActivityItem, activity_item_id)
    if item is None:
        raise ValueError(f"No activity_items row for id={activity_item_id}")
    await session.delete(item)
