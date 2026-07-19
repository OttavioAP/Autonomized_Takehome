from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api import auth, pages

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Team Activity Monitor")

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

app.include_router(pages.router)
app.include_router(auth.router)


@app.exception_handler(HTTPException)
async def redirect_unauthenticated_page_requests(request: Request, exc: HTTPException):
    if exc.status_code == status.HTTP_401_UNAUTHORIZED and "text/html" in request.headers.get(
        "accept", ""
    ):
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    return await http_exception_handler(request, exc)
