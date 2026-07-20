"""convert messages.role to native enum

Revision ID: 21c775806b64
Revises: b5880cd4a5e8
Create Date: 2026-07-20 05:14:12.880575

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "21c775806b64"
down_revision: str | Sequence[str] | None = "b5880cd4a5e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


message_role_enum = sa.Enum("user", "assistant", "system", name="messagerole")


def upgrade() -> None:
    """Upgrade schema."""
    # Autogenerate's plain alter_column only emits the ALTER TABLE ... TYPE cast, not the
    # CREATE TYPE the Postgres enum needs first - added by hand.
    message_role_enum.create(op.get_bind())
    op.alter_column(
        "messages",
        "role",
        existing_type=sa.VARCHAR(),
        type_=message_role_enum,
        postgresql_using="role::messagerole",
        existing_nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "messages",
        "role",
        existing_type=message_role_enum,
        type_=sa.VARCHAR(),
        existing_nullable=False,
    )
    message_role_enum.drop(op.get_bind())
