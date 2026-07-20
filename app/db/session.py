from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings


class Database:
    def __init__(self, url: str, **engine_kwargs: Any) -> None:
        self._engine: AsyncEngine = create_async_engine(url, **engine_kwargs)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self._session_factory() as session:
            yield session

    def new_session(self) -> AsyncSession:
        """A standalone session outside the FastAPI Depends() lifecycle - for callers
        that need their own independent transaction (e.g. concurrent work sharing no
        session, since AsyncSession isn't safe for concurrent use from multiple
        coroutines). Caller is responsible for commit/close, typically via
        `async with`."""
        return self._session_factory()

    async def dispose(self) -> None:
        await self._engine.dispose()


settings = get_settings()

db = Database(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=1800,
)
