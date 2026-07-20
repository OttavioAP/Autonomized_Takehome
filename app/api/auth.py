import secrets
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import oauth as oauth_routes
from app.auth import oidc
from app.auth.dependency import SESSION_COOKIE_NAME, get_current_user
from app.config import get_settings
from app.db.models.session import UserSession
from app.db.session import db
from app.repositories import team_member_repo

router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_LIFETIME = timedelta(hours=8)
OAUTH_STATE_COOKIE_NAME = "oauth_state"


@router.get("/login")
async def login():
    settings = get_settings()
    state = oidc.generate_state()
    authorize_url = oidc.build_authorize_url(
        tenant_id=settings.azure_tenant_id,
        client_id=settings.azure_client_id,
        redirect_uri=settings.azure_redirect_uri,
        state=state,
    )
    response = RedirectResponse(url=authorize_url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        OAUTH_STATE_COOKIE_NAME,
        state,
        httponly=True,
        secure=settings.app_env != "development",
        samesite="lax",
        max_age=600,
    )
    return response


@router.get("/callback")
async def callback(
    request: Request,
    code: str,
    state: str,
    db_session: AsyncSession = Depends(db.get_session),
):
    expected_state = request.cookies.get(OAUTH_STATE_COOKIE_NAME)
    if expected_state is None or not secrets.compare_digest(expected_state, state):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state")

    settings = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        tokens = await oidc.exchange_code_for_tokens(
            client,
            tenant_id=settings.azure_tenant_id,
            client_id=settings.azure_client_id,
            client_secret=settings.azure_client_secret,
            redirect_uri=settings.azure_redirect_uri,
            code=code,
        )
        jwks = await oidc.fetch_jwks(client, settings.azure_tenant_id)

    try:
        claims = oidc.validate_id_token(
            tokens["id_token"], jwks, settings.azure_tenant_id, settings.azure_client_id
        )
    except oidc.TokenValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ID token"
        ) from exc

    now = datetime.now(UTC)
    session = UserSession(
        id=uuid.uuid4(),
        user_upn=claims.get("preferred_username", claims["sub"]),
        user_display_name=claims.get("name", claims.get("preferred_username", "Unknown")),
        csrf_token=secrets.token_urlsafe(32),
        created_at=now,
        expires_at=now + SESSION_LIFETIME,
    )
    db_session.add(session)
    await db_session.commit()

    # oauth-integration.md's Connect prompt: only route through /oauth/connect if this
    # user is missing a JIRA/GitHub connection (first login ever, or after a disconnect/
    # revocation) - a returning user with both already connected goes straight to /,
    # since connections now persist across logins.
    redirect_target = "/"
    team_member = await team_member_repo.get_by_azure_upn(db_session, session.user_upn)
    if team_member is not None and not await oauth_routes.both_connected(
        db_session, team_member.id
    ):
        redirect_target = "/oauth/connect"

    response = RedirectResponse(url=redirect_target, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        str(session.id),
        httponly=True,
        secure=settings.app_env != "development",
        samesite="lax",
        max_age=int(SESSION_LIFETIME.total_seconds()),
    )
    response.delete_cookie(OAUTH_STATE_COOKIE_NAME)
    return response


@router.post("/logout")
async def logout(
    csrf_token: str = Form(...),
    current_user: UserSession = Depends(get_current_user),
    db_session: AsyncSession = Depends(db.get_session),
):
    if not secrets.compare_digest(current_user.csrf_token, csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")

    await db_session.execute(
        update(UserSession)
        .where(UserSession.id == current_user.id)
        .values(revoked_at=datetime.now(UTC))
    )
    await db_session.commit()

    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response
