"""HLS / M3U8 playlist parser for X Spaces streams.

Design notes
------------
Twitter Spaces use a two-level HLS structure:

1. **Master playlist** — one or more ``#EXT-X-STREAM-INF`` variant entries.
   We select the highest-bandwidth variant (typically the only one for audio).

2. **Media playlist** — lists every ``#EXTINF`` audio segment (.aac chunks).

We use the ``m3u8`` library for parsing and build absolute URLs via
``urllib.parse.urljoin`` so relative URIs are resolved correctly.
"""

import logging
from typing import List
from urllib.parse import urljoin

import aiohttp
import m3u8

from .exceptions import APIError
from .models import SegmentInfo

logger = logging.getLogger(__name__)


async def _fetch_text(session: aiohttp.ClientSession, url: str) -> str:
    """GET *url* and return the response body as text.

    Raises :class:`APIError` on non-200 responses.
    """
    try:
        resp = await session.get(url)
    except aiohttp.ClientError as exc:
        raise APIError(f"Network error fetching {url!r}: {exc}") from exc

    if resp.status != 200:
        raise APIError(f"HTTP {resp.status} fetching playlist: {url!r}")

    return await resp.text()


async def _resolve_media_playlist_url(
    session: aiohttp.ClientSession,
    url: str,
) -> str:
    """If *url* is a master playlist, return the best-quality variant URL.

    If it is already a media playlist, return it unchanged.
    """
    content = await _fetch_text(session, url)
    playlist = m3u8.loads(content)

    if not playlist.is_variant:
        # Already a media playlist.
        return url

    if not playlist.playlists:
        raise APIError("Master playlist has no variant streams")

    # Pick the variant with the highest declared bandwidth.
    best = max(
        playlist.playlists,
        key=lambda p: (p.stream_info.bandwidth if p.stream_info else 0),
    )
    media_url = urljoin(url, best.uri)
    bw = best.stream_info.bandwidth if best.stream_info else "unknown"
    logger.debug("Selected variant (bandwidth=%s): %s", bw, best.uri)
    return media_url


async def get_all_segments(
    session: aiohttp.ClientSession,
    m3u8_url: str,
) -> List[SegmentInfo]:
    """Fetch and parse all audio segments from an HLS stream.

    Handles both master playlists and direct media playlists.

    Returns a list of :class:`SegmentInfo` objects in playlist order.
    """
    # Step 1 — resolve to a media playlist URL.
    media_url = await _resolve_media_playlist_url(session, m3u8_url)

    # Step 2 — parse the media playlist.
    content = await _fetch_text(session, media_url)
    playlist = m3u8.loads(content)

    if not playlist.segments:
        raise APIError(
            "No segments found in HLS media playlist. "
            "The Space may still be processing or the replay URL has expired."
        )

    segments = [
        SegmentInfo(
            url=urljoin(media_url, seg.uri),
            index=i,
            duration=float(seg.duration or 0),
        )
        for i, seg in enumerate(playlist.segments)
    ]

    total_dur = sum(s.duration for s in segments)
    logger.info(
        "Playlist parsed: %d segments, total ~%.0f s",
        len(segments),
        total_dur,
    )
    return segments


def total_duration(segments: List[SegmentInfo]) -> float:
    """Return the sum of all segment durations in seconds."""
    return sum(s.duration for s in segments)
