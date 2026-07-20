from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import oauth as oauth_routes
from app.auth.dependency import get_current_user
from app.db.models.session import UserSession
from app.db.session import db
from app.repositories import team_member_repo
from app.templating import templates

router = APIRouter()


@router.get("/")
async def index(
    request: Request,
    current_user: UserSession = Depends(get_current_user),
    db_session: AsyncSession = Depends(db.get_session),
):
    # Server-side enforcement of the same gate app/api/auth.py's callback redirects
    # through - a user navigating straight to / (not just the post-login redirect path)
    # must not reach a page that assumes both providers are connected. GET /conversations/
    # {id} (chat.md, not built yet) is the real eventual home for this check; index.html
    # is the closest existing stand-in until that route exists.
    team_member = await team_member_repo.get_by_azure_upn(db_session, current_user.user_upn)
    if team_member is not None and not await oauth_routes.both_connected(
        db_session, team_member.id
    ):
        return RedirectResponse(url="/oauth/connect", status_code=302)

    return templates.TemplateResponse(
        request=request, name="index.html", context={"current_user": current_user}
    )


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={})


@router.get("/ping")
async def ping(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="_ping_result.html",
        context={"timestamp": datetime.now(UTC).isoformat()},
    )
