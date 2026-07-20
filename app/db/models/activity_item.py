import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ActivityItem(Base):
    __tablename__ = "activity_items"
    __table_args__ = (UniqueConstraint("conversation_id", "kind", "external_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id"), nullable=False
    )
    # "jira_ticket" | "github_commit" | "github_pr" (app.schemas.chat.ActivityKind, not yet
    # built as of this table's creation) — plain str/String until that enum type exists.
    kind: Mapped[str] = mapped_column(String, nullable=False)
    # JIRA key (e.g. "KAN-42") or a GitHub PR number / commit SHA.
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
