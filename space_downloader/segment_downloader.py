"""Async parallel segment downloader with retry and resume support.

Design notes
------------
- Uses ``asyncio.Semaphore`` to cap concurrent connections to *max_concurrent*.
- Each segment is retried up to ``MAX_RETRIES`` times with exponential back-off.
- Segments already present on disk (non-zero size) are skipped — this enables
  resuming an interrupted download without re-fetching anything.
- A >10% failure rate raises :class:`SegmentDownloadError`; lower failure rates
  emit a warning and continue (the merger handles missing segments gracefully).
"""

import asyncio
import logging
from pathlib import Path
from typing import Callable, List, Optional

import aiohttp
from rich.progress import Progress, TaskID

from .exceptions import SegmentDownloadError
from .models import SegmentInfo
from .utils import format_bytes, url_to_filename

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
_RETRY_BASE_DELAY = 1.0  # seconds — doubled each attempt (exponential back-off)
MAX_CONCURRENT_DEFAULT = 8


async def _download_one(
    session: aiohttp.ClientSession,
    segment: SegmentInfo,
    output_dir: Path,
    semaphore: asyncio.Semaphore,
    progress: Progress,
    task_id: TaskID,
    on_bytes: Optional[Callable[[int], None]] = None,
) -> bool:
    """Download a single segment.

    Returns ``True`` on success, ``False`` after all retries are exhausted.
    """
    local_path = output_dir / url_to_filename(segment.url)

    # Resume: skip segments already on disk with valid content.
    if local_path.exists() and local_path.stat().st_size > 0:
        data = local_path.read_bytes()
        if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and (data[1] & 0xF0) == 0xF0):
            segment.local_path = local_path
            segment.downloaded = True
            progress.advance(task_id)
            return True
        # File exists but is corrupt — delete and re-download.
        logger.warning("Segment %d: cached file is corrupt, re-downloading…", segment.index)
        local_path.unlink()

    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                async with session.get(segment.url) as resp:
                    if resp.status != 200:
                        raise aiohttp.ClientResponseError(
                            resp.request_info,
                            resp.history,
                            status=resp.status,
                        )
                    data = await resp.read()

                # Sanity-check: Twitter Space segments start with ID3 or ADTS sync.
                if len(data) < 4 or not (
                    data[:3] == b"ID3"
                    or (data[0] == 0xFF and (data[1] & 0xF0) == 0xF0)
                ):
                    raise ValueError(
                        f"Segment {segment.index} response is not valid AAC "
                        f"(got {data[:4].hex()!r})"
                    )

                local_path.write_bytes(data)
                segment.local_path = local_path
                segment.downloaded = True
                segment.download_attempts = attempt + 1

                progress.advance(task_id)
                if on_bytes:
                    on_bytes(len(data))
                return True

            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
                segment.download_attempts = attempt + 1
                delay = _RETRY_BASE_DELAY * (2 ** attempt)

                if attempt < MAX_RETRIES - 1:
                    logger.warning(
                        "Segment %d – attempt %d/%d failed (%s). Retrying in %.1fs…",
                        segment.index,
                        attempt + 1,
                        MAX_RETRIES,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Segment %d – gave up after %d attempts: %s",
                        segment.index,
                        MAX_RETRIES,
                        exc,
                    )
                    return False

    return False  # unreachable, but satisfies type checkers


async def download_segments(
    segments: List[SegmentInfo],
    output_dir: Path,
    max_concurrent: int = MAX_CONCURRENT_DEFAULT,
    progress: Optional[Progress] = None,
    overall_task: Optional[TaskID] = None,
) -> List[SegmentInfo]:
    """Download all *segments* concurrently and return the successful ones.

    Args:
        segments:       Segment list from :func:`hls_parser.get_all_segments`.
        output_dir:     Directory where segment files are written.
        max_concurrent: Maximum simultaneous HTTP connections.
        progress:       Rich :class:`Progress` instance for live UI updates.
        overall_task:   Task ID inside *progress* to advance per segment.

    Returns:
        The subset of *segments* that were successfully downloaded, in order.

    Raises:
        :class:`SegmentDownloadError`: if more than 10 % of segments fail.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Fallback progress/task when called outside a Rich context.
    if progress is None or overall_task is None:
        from rich.progress import Progress as _P
        _dummy = _P()
        _dummy.start()
        _p: Progress = _dummy
        _t: TaskID = _p.add_task("Downloading…", total=len(segments))
    else:
        _p, _t = progress, overall_task

    semaphore = asyncio.Semaphore(max_concurrent)
    total_bytes = 0

    def _on_bytes(n: int) -> None:
        nonlocal total_bytes
        total_bytes += n

    timeout = aiohttp.ClientTimeout(total=120, connect=10, sock_read=60)
    connector = aiohttp.TCPConnector(limit=max_concurrent * 2)

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        tasks = [
            _download_one(session, seg, output_dir, semaphore, _p, _t, _on_bytes)
            for seg in segments
        ]
        results: List[bool] = await asyncio.gather(*tasks)

    failed = [seg for seg, ok in zip(segments, results) if not ok]
    if failed:
        failure_rate = len(failed) / len(segments)
        msg = f"{len(failed)}/{len(segments)} segments failed to download"
        if failure_rate > 0.10:
            raise SegmentDownloadError(
                f"{msg} (>{failure_rate:.0%}). "
                "Check your connection or try again. The output may be corrupted."
            )
        logger.warning("%s — output may have gaps", msg)

    successful = [seg for seg in segments if seg.downloaded and seg.local_path]
    logger.info(
        "Downloaded %d/%d segments (%s total)",
        len(successful),
        len(segments),
        format_bytes(total_bytes),
    )
    return successful
