from datetime import UTC, datetime

from fastapi import APIRouter, Request

from app.templating import templates

router = APIRouter()


@router.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})


@router.get("/ping")
async def ping(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="_ping_result.html",
        context={"timestamp": datetime.now(UTC).isoformat()},
    )
