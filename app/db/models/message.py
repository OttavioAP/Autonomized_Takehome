import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id"), nullable=False
    )
    # values_callable stores each member's .value ("user") in Postgres, not the default
    # SQLAlchemy behavior of storing the Python member .name ("USER") — keeps the DB enum
    # labels matching the wire/API vocabulary (Literal["user", "assistant", "system"] in
    # the future app/schemas/chat.py) rather than diverging from it.
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, values_callable=lambda enum_cls: [member.value for member in enum_cls]),
        nullable=False,
    )
    # Raw text with citation sentinels embedded (e.g. "{{cite:1:<uuid>}}") — nothing
    # enforced at the DB level about this format.
    content: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
