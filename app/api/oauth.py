"""Per-user JIRA/GitHub OAuth connect/disconnect routes (oauth-integration.md's
"Connect/disconnect UI + routes" section). Mirrors app/api/auth.py's Azure flow shape
(login -> redirect -> callback -> store), but writes into Key Vault keyed by
team_member_id instead of a session table column, and the "session" here is the
already-authenticated Azure SSO session - these routes never establish identity
themselves, only add JIRA/GitHub connections on top of it.
"""

import secrets
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependency import get_current_user
from app.config import get_settings
from app.db.models.session import UserSession
from app.db.session import db
from app.repositories import team_member_repo
from app.services import token_store
from app.templating import templates

router = APIRouter(prefix="/oauth", tags=["oauth"])

OAUTH_STATE_COOKIE_NAME = "oauth_state"

JIRA_AUTHORIZE_URL = "https://auth.atlassian.com/authorize"
JIRA_ACCESSIBLE_RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"

# offline_access requests the refresh token oauth-integration.md's silent-refresh design
# (jira_client.refresh_access_token) requires.
JIRA_SCOPES = "read:jira-work read:jira-user offline_access"
GITHUB_SCOPES = "repo"


async def _get_team_member_id(session: AsyncSession, current_user: UserSession) -> Any:
    """Every route below needs the team_members row backing the current Azure session -
    same azure_upn join chat.md's pre-fetch uses. 404s rather than 401ing since the user
    IS authenticated (Azure SSO passed); they're just not a seeded team member, a
    different failure mode than "not logged in".
    """
    team_member = await team_member_repo.get_by_azure_upn(session, current_user.user_upn)
    if team_member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No team member record for this account"
        )
    return team_member.id


@router.get("/connect")
async def connect_page(
    request: Request,
    current_user: UserSession = Depends(get_current_user),
    db_session: AsyncSession = Depends(db.get_session),
):
    team_member_id = await _get_team_member_id(db_session, current_user)
    jira_tokens = await token_store.get_jira_tokens(team_member_id)
    github_token = await token_store.get_github_token(team_member_id)
    return templates.TemplateResponse(
        request=request,
        name="oauth_connect.html",
        context={
            "current_user": current_user,
            "jira_connected": jira_tokens is not None,
            "github_connected": github_token is not None,
        },
    )


@router.get("/jira/connect")
async def jira_connect(
    current_user: UserSession = Depends(get_current_user),
):
    settings = get_settings()
    state = secrets.token_urlsafe(32)
    params = {
        "audience": "api.atlassian.com",
        "client_id": settings.jira_oauth_client_id,
        "scope": JIRA_SCOPES,
        "redirect_uri": settings.jira_oauth_redirect_uri,
        "state": state,
        "response_type": "code",
        "prompt": "consent",
    }
    response = RedirectResponse(
        url=f"{JIRA_AUTHORIZE_URL}?{urlencode(params)}", status_code=status.HTTP_302_FOUND
    )
    response.set_cookie(
        OAUTH_STATE_COOKIE_NAME,
        state,
        httponly=True,
        secure=settings.app_env != "development",
        samesite="lax",
        max_age=600,
    )
    return response


@router.get("/jira/callback")
async def jira_callback(
    request: Request,
    code: str,
    state: str,
    current_user: UserSession = Depends(get_current_user),
    db_session: AsyncSession = Depends(db.get_session),
):
    expected_state = request.cookies.get(OAUTH_STATE_COOKIE_NAME)
    if expected_state is None or not secrets.compare_digest(expected_state, state):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state")

    settings = get_settings()
    team_member_id = await _get_team_member_id(db_session, current_user)

    async with httpx.AsyncClient(timeout=10.0) as client:
        token_resp = await client.post(
            "https://auth.atlassian.com/oauth/token",
            json={
                "grant_type": "authorization_code",
                "client_id": settings.jira_oauth_client_id,
                "client_secret": settings.jira_oauth_client_secret,
                "code": code,
                "redirect_uri": settings.jira_oauth_redirect_uri,
            },
        )
        token_resp.raise_for_status()
        tokens = token_resp.json()

        resources_resp = await client.get(
            JIRA_ACCESSIBLE_RESOURCES_URL,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        resources_resp.raise_for_status()
        resources = resources_resp.json()

    if not resources:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No accessible JIRA site for this account",
        )
    # Multi-site JIRA (a user with access to more than one Atlassian site) beyond taking
    # the first result is explicitly out of scope per oauth-integration.md. `url` here
    # is the site's real browse URL (e.g. https://foo.atlassian.net) - distinct from
    # `id` (cloud_id), which only builds the API base URL; JiraTool needs both, one for
    # API calls, one for building activity_items.url deep-links.
    cloud_id = resources[0]["id"]
    site_url = resources[0]["url"]

    await token_store.store_jira_tokens(
        team_member_id, tokens["access_token"], tokens["refresh_token"]
    )
    await team_member_repo.set_jira_cloud_id(db_session, team_member_id, cloud_id, site_url)
    await db_session.commit()

    response = RedirectResponse(url="/oauth/connect", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(OAUTH_STATE_COOKIE_NAME)
    return response


@router.get("/github/connect")
async def github_connect(
    current_user: UserSession = Depends(get_current_user),
):
    settings = get_settings()
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": settings.github_oauth_client_id,
        "redirect_uri": settings.github_oauth_redirect_uri,
        "scope": GITHUB_SCOPES,
        "state": state,
    }
    response = RedirectResponse(
        url=f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}", status_code=status.HTTP_302_FOUND
    )
    response.set_cookie(
        OAUTH_STATE_COOKIE_NAME,
        state,
        httponly=True,
        secure=settings.app_env != "development",
        samesite="lax",
        max_age=600,
    )
    return response


@router.get("/github/callback")
async def github_callback(
    request: Request,
    code: str,
    state: str,
    current_user: UserSession = Depends(get_current_user),
    db_session: AsyncSession = Depends(db.get_session),
):
    expected_state = request.cookies.get(OAUTH_STATE_COOKIE_NAME)
    if expected_state is None or not secrets.compare_digest(expected_state, state):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state")

    settings = get_settings()
    team_member_id = await _get_team_member_id(db_session, current_user)

    async with httpx.AsyncClient(timeout=10.0) as client:
        token_resp = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": settings.github_oauth_client_id,
                "client_secret": settings.github_oauth_client_secret,
                "code": code,
                "redirect_uri": settings.github_oauth_redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        token_resp.raise_for_status()
        tokens = token_resp.json()

    if "access_token" not in tokens:
        # GitHub returns 200 with an error body (e.g. bad_verification_code) rather than
        # a non-2xx status on failure, so raise_for_status() above wouldn't catch this.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"GitHub token exchange failed: {tokens.get('error', 'unknown error')}",
        )

    await token_store.store_github_token(team_member_id, tokens["access_token"])

    response = RedirectResponse(url="/oauth/connect", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(OAUTH_STATE_COOKIE_NAME)
    return response


@router.post("/jira/disconnect")
async def jira_disconnect(
    csrf_token: str = Form(...),
    current_user: UserSession = Depends(get_current_user),
    db_session: AsyncSession = Depends(db.get_session),
):
    if not secrets.compare_digest(current_user.csrf_token, csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")

    team_member_id = await _get_team_member_id(db_session, current_user)
    await token_store.delete_jira_tokens(team_member_id)
    return RedirectResponse(url="/oauth/connect", status_code=status.HTTP_302_FOUND)


@router.post("/github/disconnect")
async def github_disconnect(
    csrf_token: str = Form(...),
    current_user: UserSession = Depends(get_current_user),
    db_session: AsyncSession = Depends(db.get_session),
):
    if not secrets.compare_digest(current_user.csrf_token, csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")

    team_member_id = await _get_team_member_id(db_session, current_user)
    await token_store.delete_github_token(team_member_id)
    return RedirectResponse(url="/oauth/connect", status_code=status.HTTP_302_FOUND)


async def both_connected(session: AsyncSession, team_member_id: Any) -> bool:
    """GET /auth/callback's gate check: both providers connected -> skip the /oauth/connect
    interstitial and go straight to /. Exported for app/api/auth.py to import rather than
    duplicating Key Vault lookups there.
    """
    jira_tokens = await token_store.get_jira_tokens(team_member_id)
    github_token = await token_store.get_github_token(team_member_id)
    return jira_tokens is not None and github_token is not None
