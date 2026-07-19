import secrets
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.dependency import SESSION_COOKIE_NAME
from app.db.models.session import UserSession
from app.db.session import db
from app.main import app


@pytest.fixture(autouse=True)
async def _dispose_db_pool_after_test() -> AsyncGenerator[None, None]:
    # pytest-asyncio uses a fresh event loop per test function, but app.db.session.db
    # is a module-level singleton whose pooled connections get bound to whichever
    # loop created them. Without disposing the pool here, a connection opened in one
    # test's loop can be handed to a later test running on a different loop, which
    # asyncpg rejects. Only needed for tests that touch the DB directly outside the
    # ASGI app's own per-request session lifecycle (e.g. the authenticated_client
    # fixture below).
    yield
    await db.dispose()


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def authenticated_client(client: AsyncClient) -> AsyncGenerator[AsyncClient, None]:
    now = datetime.now(UTC)
    session = UserSession(
        id=uuid.uuid4(),
        user_upn="john@ottavioantperuzzigmail.onmicrosoft.com",
        user_display_name="John",
        csrf_token=secrets.token_urlsafe(32),
        created_at=now,
        expires_at=now + timedelta(hours=8),
    )
    async for db_session in db.get_session():
        db_session.add(session)
        await db_session.commit()

    client.cookies.set(SESSION_COOKIE_NAME, str(session.id))
    yield client
