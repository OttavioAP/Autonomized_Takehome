from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import pages

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Team Activity Monitor")

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

app.include_router(pages.router)
