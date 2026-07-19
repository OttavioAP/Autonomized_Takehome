from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request

from app.auth.dependency import get_current_user
from app.db.models.session import UserSession
from app.templating import templates

router = APIRouter()


@router.get("/")
async def index(request: Request, current_user: UserSession = Depends(get_current_user)):
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
