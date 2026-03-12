"""FastAPI application factory for the X Spaces Downloader web UI."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routes import router

BASE = Path(__file__).parent
DOWNLOADS = BASE / "downloads"
DOWNLOADS.mkdir(exist_ok=True)

app = FastAPI(title="X Spaces Downloader", docs_url=None, redoc_url=None)

app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
app.mount("/downloads", StaticFiles(directory=DOWNLOADS), name="downloads")
app.include_router(router)
