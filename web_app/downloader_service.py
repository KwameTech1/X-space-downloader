"""Bridge between the FastAPI web layer and the existing downloader engine.

Each download is a ``DownloadJob`` tracked by a short UUID.  The job runs as
an asyncio task inside FastAPI's event loop.  Blocking operations (ffmpeg
merge, metadata tagging) are dispatched to a thread-pool executor so they
don't freeze the server.

Progress events are pushed into a per-job ``asyncio.Queue``; the WebSocket
route drains that queue and forwards every message to the browser.
"""

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp

from space_downloader.audio_merger import check_ffmpeg, merge_segments
from space_downloader.hls_parser import get_all_segments, total_duration
from space_downloader.metadata import tag_audio_file
from space_downloader.models import SpaceMetadata
from space_downloader.segment_downloader import download_segments
from space_downloader.twitter_api import TwitterAPIClient
from space_downloader.utils import extract_space_id, format_duration, make_safe_filename

DOWNLOADS_DIR = Path(__file__).parent / "downloads"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass
class DownloadJob:
    job_id: str
    url: str
    transcribe: bool = False
    transcribe_model: str = "small"
    language: Optional[str] = None
    status: JobStatus = JobStatus.PENDING
    result_file: Optional[Path] = None
    error: Optional[str] = None
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    created_at: datetime = field(default_factory=datetime.utcnow)

    async def emit(self, event_type: str, data: Any = None) -> None:
        await self.queue.put({"type": event_type, "data": data})


class JobManager:
    def __init__(self) -> None:
        self._jobs: Dict[str, DownloadJob] = {}

    def create(
        self,
        url: str,
        transcribe: bool = False,
        transcribe_model: str = "small",
        language: Optional[str] = None,
    ) -> DownloadJob:
        job_id = str(uuid.uuid4())[:8]
        job = DownloadJob(
            job_id=job_id,
            url=url,
            transcribe=transcribe,
            transcribe_model=transcribe_model,
            language=language,
        )
        self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Optional[DownloadJob]:
        return self._jobs.get(job_id)


job_manager = JobManager()


async def run_download(job: DownloadJob) -> None:
    """Execute the full download pipeline for *job*, emitting progress events."""
    job.status = JobStatus.RUNNING
    loop = asyncio.get_event_loop()

    try:
        check_ffmpeg()

        space_id = extract_space_id(job.url)
        job_dir = DOWNLOADS_DIR / job.job_id
        seg_dir = job_dir / "segments"
        job_dir.mkdir(parents=True, exist_ok=True)

        # ── 1. Metadata ───────────────────────────────────────────────────────
        await job.emit("log", "Fetching Space metadata…")
        async with TwitterAPIClient() as client:
            metadata: SpaceMetadata = await client.get_space_metadata(space_id)
            stream_url: str = await client.get_stream_url(metadata.media_key)

        dur_str = format_duration(metadata.duration_seconds) if metadata.duration_seconds else None
        await job.emit("metadata", {
            "title": metadata.title,
            "host": f"@{metadata.host_username} ({metadata.host_display_name})",
            "state": metadata.state,
            "duration": dur_str,
        })

        # ── 2. Parse HLS playlist ─────────────────────────────────────────────
        await job.emit("log", "Parsing HLS playlist…")
        async with aiohttp.ClientSession() as session:
            segments = await get_all_segments(session, stream_url)

        total = len(segments)
        dur_total = total_duration(segments)
        await job.emit("log", f"Found {total} segments (~{format_duration(dur_total)})")
        await job.emit("segments_total", total)

        # ── 3. Download ───────────────────────────────────────────────────────
        await job.emit("log", f"Downloading {total} segments…")
        downloaded = await download_segments(segments, seg_dir)
        await job.emit("log", f"Downloaded {len(downloaded)}/{total} segments")
        await job.emit("download_done", {"downloaded": len(downloaded), "total": total})

        # ── 4. Merge (blocking — offloaded to thread pool) ────────────────────
        await job.emit("log", "Merging audio… (this may take a few minutes)")
        safe_title = make_safe_filename(metadata.title or f"space_{space_id}")
        output_base = job_dir / safe_title
        output_path: Path = await loop.run_in_executor(
            None,
            lambda: merge_segments(
                downloaded, output_base, output_format="mp3", cleanup_segments=True
            ),
        )

        # ── 5. Tag (blocking) ─────────────────────────────────────────────────
        await job.emit("log", "Embedding metadata tags…")
        try:
            await loop.run_in_executor(
                None, lambda: tag_audio_file(output_path, metadata, "mp3")
            )
        except Exception:
            pass  # tagging failure is non-fatal

        size_mb = round(output_path.stat().st_size / 1_000_000, 1)
        job.result_file = output_path
        job.status = JobStatus.DONE

        await job.emit("done", {
            "filename": output_path.name,
            "size_mb": size_mb,
            "url": f"/downloads/{job.job_id}/{output_path.name}",
        })

        # ── 6–8. Transcription pipeline (optional) ────────────────────────────
        if job.transcribe:
            from transcription.transcriber import transcribe_audio
            from transcription.transcript_cleaner import clean_transcript
            from analysis.summarizer import summarize_transcript

            await job.emit("log", f"Transcribing with Whisper '{job.transcribe_model}'…")
            await job.emit("transcribe_start", None)
            try:
                transcript_path: Path = await loop.run_in_executor(
                    None,
                    lambda: transcribe_audio(
                        output_path,
                        model_size=job.transcribe_model,
                        language=job.language,
                    ),
                )
                await job.emit("log", f"Transcript ready: {transcript_path.name}")
                await job.emit("transcript_done", {
                    "filename": transcript_path.name,
                    "url": f"/downloads/{job.job_id}/{transcript_path.name}",
                })
            except Exception as exc:
                await job.emit("log", f"Transcription failed: {exc}")
                return  # can't clean/summarise without a transcript

            has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
            if not has_key:
                await job.emit("log", "Set ANTHROPIC_API_KEY to enable cleaning & summary.")
                return

            await job.emit("log", "Cleaning transcript…")
            try:
                clean_path: Path = await loop.run_in_executor(
                    None, lambda: clean_transcript(transcript_path)
                )
                await job.emit("log", f"Clean transcript ready: {clean_path.name}")
                await job.emit("clean_done", {
                    "filename": clean_path.name,
                    "url": f"/downloads/{job.job_id}/{clean_path.name}",
                })
            except Exception as exc:
                await job.emit("log", f"Transcript cleaning failed: {exc}")
                clean_path = transcript_path  # fall back to raw transcript

            await job.emit("log", "Generating summary…")
            try:
                summary_path: Path = await loop.run_in_executor(
                    None, lambda: summarize_transcript(clean_path, metadata=metadata)
                )
                await job.emit("log", f"Summary ready: {summary_path.name}")
                await job.emit("summary_done", {
                    "filename": summary_path.name,
                    "url": f"/downloads/{job.job_id}/{summary_path.name}",
                })
            except Exception as exc:
                await job.emit("log", f"Summarization failed: {exc}")

    except Exception as exc:
        job.status = JobStatus.ERROR
        job.error = str(exc)
        await job.emit("error", str(exc))
