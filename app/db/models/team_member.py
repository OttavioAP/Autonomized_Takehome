import uuid

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TeamMember(Base):
    __tablename__ = "team_members"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    azure_upn: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    jira_account_email: Mapped[str] = mapped_column(String, nullable=False)
    github_login: Mapped[str] = mapped_column(String, nullable=False)
    # Resolved once via accessible-resources at GET /oauth/jira/callback time, reused
    # by pre-fetch so it's never re-derived on every tool call. NULL until the user
    # connects JIRA (see oauth-integration.md's Token storage / Connect prompt sections).
    jira_cloud_id: Mapped[str | None] = mapped_column(String, nullable=True)
