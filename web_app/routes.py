"""HTTP and WebSocket routes for the web UI."""

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .downloader_service import JobStatus, job_manager, run_download

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@router.post("/api/download")
async def start_download(payload: dict) -> dict:
    url = (payload.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    job = job_manager.create(url)
    asyncio.create_task(run_download(job))
    return {"job_id": job.job_id}


@router.websocket("/ws/{job_id}")
async def ws_progress(websocket: WebSocket, job_id: str) -> None:
    """Stream progress events to the browser until the job finishes."""
    await websocket.accept()
    job = job_manager.get(job_id)
    if not job:
        await websocket.send_json({"type": "error", "data": "Job not found"})
        await websocket.close()
        return

    try:
        while True:
            try:
                msg = await asyncio.wait_for(job.queue.get(), timeout=120)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
                continue

            await websocket.send_json(msg)
            if msg["type"] in ("done", "error"):
                break
    except WebSocketDisconnect:
        pass
    finally:
        await websocket.close()


@router.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job.job_id,
        "status": job.status,
        "error": job.error,
        "file_url": (
            f"/downloads/{job.job_id}/{job.result_file.name}"
            if job.result_file else None
        ),
    }
