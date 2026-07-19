"""Single shared auth enforcement point (stack-and-infra.md: "one enforcement point,
not duplicated logic"). Used via Depends() on every protected page/fragment route.
"""

import uuid
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.session import UserSession
from app.db.session import db

SESSION_COOKIE_NAME = "session_id"


async def get_current_user(
    request: Request, db_session: AsyncSession = Depends(db.get_session)
) -> UserSession:
    raw_session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if raw_session_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        session_id = uuid.UUID(raw_session_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        ) from exc

    result = await db_session.execute(select(UserSession).where(UserSession.id == session_id))
    session = result.scalar_one_or_none()

    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if session.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session revoked")
    if session.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    return session
