from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SmokeTest(Base):
    """Throwaway table proving the Alembic pipeline end-to-end; delete once a real model exists."""

    __tablename__ = "alembic_smoke_test"

    id: Mapped[int] = mapped_column(primary_key=True)
