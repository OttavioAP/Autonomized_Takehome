import uuid

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TeamMember(Base):
    __tablename__ = "team_members"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    azure_upn: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    # Seed-time default identity, per local-dev-data/team_members.json - not an
    # enforced identity; superseded by jira_account_id once the user actually
    # connects (see jira_account_id below and app/api/oauth.py's jira_callback).
    jira_account_email: Mapped[str] = mapped_column(String, nullable=False)
    github_login: Mapped[str] = mapped_column(String, nullable=False)
    # Resolved once via /rest/api/3/myself at GET /oauth/jira/callback time - the
    # account that actually authorized, which may differ from the seeded
    # jira_account_email above (any Atlassian account can be linked by connecting
    # it, per oauth-integration.md). NULL until the user connects JIRA; preferred
    # over jira_account_email everywhere once set, since account_id is unambiguous
    # while email lookup can silently resolve to the wrong (or no) account.
    jira_account_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Resolved once via accessible-resources at GET /oauth/jira/callback time, reused
    # by pre-fetch so it's never re-derived on every tool call. NULL until the user
    # connects JIRA (see oauth-integration.md's Token storage / Connect prompt sections).
    jira_cloud_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # The site's real browse URL (e.g. https://foo.atlassian.net), also from
    # accessible-resources - distinct from jira_cloud_id, which only builds the API base
    # URL (api.atlassian.com/ex/jira/{cloud_id}/...). Needed to build activity_items.url
    # deep-links for JIRA tickets, which the API base URL can't produce.
    jira_site_url: Mapped[str | None] = mapped_column(String, nullable=True)
