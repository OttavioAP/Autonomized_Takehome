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
from app.repositories import team_member_repo
from app.services import token_store


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
        team_member = await team_member_repo.get_by_azure_upn(db_session, session.user_upn)

    # This fixture represents a fully onboarded user, not just a logged-in one - most
    # tests using it exercise post-login behavior (logout, page rendering) that assumes
    # past the /oauth/connect gate, not the gate itself. Real Key Vault writes (this repo
    # has no mocking). Deliberately NOT deleted in teardown: Key Vault's soft-delete ->
    # purge cycle has its own backend-side eventual-consistency window (a purge doesn't
    # complete synchronously even though purge_deleted_secret's coroutine returns), so a
    # delete-then-recreate cycle on every single test run races real infrastructure state
    # - hit this directly as a flaky "currently being deleted, cannot be re-created"
    # error. Idempotent instead: only store if not already connected, so repeat runs are
    # a no-op rather than delete/recreate churn.
    assert team_member is not None, "seed data must include john@... (local-dev-data)"
    if await token_store.get_jira_tokens(team_member.id) is None:
        await token_store.store_jira_tokens(
            team_member.id, "test-access-token", "test-refresh-token"
        )
    if await token_store.get_github_token(team_member.id) is None:
        await token_store.store_github_token(team_member.id, "test-github-token")

    client.cookies.set(SESSION_COOKIE_NAME, str(session.id))
    yield client
