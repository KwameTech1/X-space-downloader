"""Tests for space_downloader.hls_parser."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from space_downloader.hls_parser import get_all_segments, total_duration
from space_downloader.models import SegmentInfo

MASTER_PLAYLIST = """\
#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=128000,CODECS="mp4a.40.2"
https://cdn.example.com/audio/media.m3u8
"""

MEDIA_PLAYLIST = """\
#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:10
#EXTINF:9.009,
https://cdn.example.com/seg000.aac
#EXTINF:9.009,
https://cdn.example.com/seg001.aac
#EXTINF:9.009,
https://cdn.example.com/seg002.aac
#EXT-X-ENDLIST
"""


def _make_session(responses: dict) -> AsyncMock:
    """Build a mock aiohttp.ClientSession that returns preset text for URLs."""

    async def fake_get(url):
        r = AsyncMock()
        r.status = 200
        r.text = AsyncMock(return_value=responses.get(url, ""))
        return r

    session = AsyncMock()
    session.get = fake_get
    return session


@pytest.mark.asyncio
async def test_get_all_segments_via_master():
    session = _make_session(
        {
            "https://cdn.example.com/master.m3u8": MASTER_PLAYLIST,
            "https://cdn.example.com/audio/media.m3u8": MEDIA_PLAYLIST,
        }
    )
    segments = await get_all_segments(session, "https://cdn.example.com/master.m3u8")

    assert len(segments) == 3
    assert all(isinstance(s, SegmentInfo) for s in segments)
    assert segments[0].index == 0
    assert segments[2].index == 2
    assert "seg000.aac" in segments[0].url
    assert "seg002.aac" in segments[2].url


@pytest.mark.asyncio
async def test_get_all_segments_direct_media_playlist():
    session = _make_session(
        {"https://cdn.example.com/audio/media.m3u8": MEDIA_PLAYLIST}
    )
    segments = await get_all_segments(session, "https://cdn.example.com/audio/media.m3u8")
    assert len(segments) == 3


@pytest.mark.asyncio
async def test_empty_playlist_raises():
    empty_playlist = "#EXTM3U\n#EXT-X-ENDLIST\n"
    session = _make_session({"https://cdn.example.com/empty.m3u8": empty_playlist})

    from space_downloader.exceptions import APIError
    with pytest.raises(APIError, match="No segments"):
        await get_all_segments(session, "https://cdn.example.com/empty.m3u8")


def test_total_duration():
    segs = [SegmentInfo(url="x", index=i, duration=9.0) for i in range(3)]
    assert total_duration(segs) == pytest.approx(27.0)
