"""One-off admin script: purge all conversations (and their dependent rows) for a
single team member, identified by their azure_upn. Deletes in FK-dependency order
since none of the chat schema's foreign keys have ON DELETE CASCADE
(message_citations -> messages/activity_items -> conversations):

    message_citations (FK -> messages.id, activity_items.id)
    messages          (FK -> conversations.id)
    activity_items    (FK -> conversations.id)
    conversations     (FK -> team_members.id)

team_members itself is never touched - only that person's conversation history and
everything scoped under it.

Defaults to a dry run (prints what would be deleted, deletes nothing) - pass
--confirm to actually execute. Real, irreversible data loss otherwise.

Usage:
    docker compose exec fastapi python scripts/purge_conversations.py <azure_upn>
    docker compose exec fastapi python scripts/purge_conversations.py <azure_upn> --confirm
"""

import argparse
import asyncio

from sqlalchemy import delete, select

from app.db.models.activity_item import ActivityItem
from app.db.models.conversation import Conversation
from app.db.models.message import Message
from app.db.models.message_citation import MessageCitation
from app.db.session import db
from app.repositories import team_member_repo


async def purge(azure_upn: str, *, confirm: bool) -> None:
    async for session in db.get_session():
        team_member = await team_member_repo.get_by_azure_upn(session, azure_upn)
        if team_member is None:
            print(f"No team_members row for azure_upn={azure_upn!r} - nothing to do.")
            return

        conv_result = await session.execute(
            select(Conversation.id).where(Conversation.team_member_id == team_member.id)
        )
        conversation_ids = [row[0] for row in conv_result.all()]
        if not conversation_ids:
            print(f"{team_member.display_name} ({azure_upn}) has no conversations - nothing to do.")
            return

        message_result = await session.execute(
            select(Message.id).where(Message.conversation_id.in_(conversation_ids))
        )
        message_ids = [row[0] for row in message_result.all()]

        activity_result = await session.execute(
            select(ActivityItem.id).where(ActivityItem.conversation_id.in_(conversation_ids))
        )
        activity_ids = [row[0] for row in activity_result.all()]

        citation_count = 0
        if message_ids:
            citation_result = await session.execute(
                select(MessageCitation.id).where(MessageCitation.message_id.in_(message_ids))
            )
            citation_count = len(citation_result.all())

        print(f"{team_member.display_name} ({azure_upn}) - team_member_id={team_member.id}")
        print(f"  conversations:      {len(conversation_ids)}")
        print(f"  messages:           {len(message_ids)}")
        print(f"  activity_items:     {len(activity_ids)}")
        print(f"  message_citations:  {citation_count}")

        if not confirm:
            print("\nDry run only - nothing deleted. Re-run with --confirm to actually purge.")
            return

        if message_ids:
            await session.execute(
                delete(MessageCitation).where(MessageCitation.message_id.in_(message_ids))
            )
        await session.execute(delete(Message).where(Message.conversation_id.in_(conversation_ids)))
        await session.execute(
            delete(ActivityItem).where(ActivityItem.conversation_id.in_(conversation_ids))
        )
        await session.execute(
            delete(Conversation).where(Conversation.team_member_id == team_member.id)
        )
        await session.commit()
        print("\nPurged.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("azure_upn", help="e.g. john@ottavioantperuzzigmail.onmicrosoft.com")
    parser.add_argument(
        "--confirm", action="store_true", help="Actually delete (default is a dry run/report)."
    )
    args = parser.parse_args()
    asyncio.run(purge(args.azure_upn, confirm=args.confirm))


if __name__ == "__main__":
    main()
