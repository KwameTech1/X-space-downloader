"""Tests for space_downloader.segment_downloader."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from space_downloader.models import SegmentInfo
from space_downloader.utils import url_to_filename


@pytest.mark.asyncio
async def test_skips_already_downloaded_segment(tmp_path):
    """A segment whose file already exists must not trigger a network request."""
    from space_downloader.segment_downloader import _download_one

    url = "https://cdn.example.com/seg001.aac"
    seg = SegmentInfo(url=url, index=0, duration=9.0)

    # Pre-create the file at the path the downloader expects.
    expected = tmp_path / url_to_filename(url)
    expected.write_bytes(b"\x00" * 128)  # non-empty fake audio data

    mock_progress = MagicMock()
    mock_session = AsyncMock()
    sem = asyncio.Semaphore(1)

    result = await _download_one(
        mock_session, seg, tmp_path, sem, mock_progress, "task_id"
    )

    assert result is True
    assert seg.downloaded is True
    assert seg.local_path == expected
    mock_session.get.assert_not_called()
    mock_progress.advance.assert_called_once()


@pytest.mark.asyncio
async def test_download_writes_file(tmp_path):
    """A successful HTTP response must write bytes to disk."""
    from space_downloader.segment_downloader import _download_one

    url = "https://cdn.example.com/seg002.aac"
    seg = SegmentInfo(url=url, index=1, duration=9.0)

    fake_data = b"fake aac audio data"
    mock_resp = AsyncMock()
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)
    mock_resp.status = 200
    mock_resp.read = AsyncMock(return_value=fake_data)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)

    mock_progress = MagicMock()
    sem = asyncio.Semaphore(1)

    result = await _download_one(
        mock_session, seg, tmp_path, sem, mock_progress, "task_id"
    )

    assert result is True
    assert seg.downloaded is True
    assert seg.local_path is not None
    assert seg.local_path.read_bytes() == fake_data


@pytest.mark.asyncio
async def test_download_segments_integration(tmp_path):
    """download_segments should return only the successfully downloaded segments."""
    import aiohttp
    from space_downloader.segment_downloader import download_segments

    url_a = "https://cdn.example.com/seg000.aac"
    url_b = "https://cdn.example.com/seg001.aac"

    segments = [
        SegmentInfo(url=url_a, index=0, duration=9.0),
        SegmentInfo(url=url_b, index=1, duration=9.0),
    ]

    # Pre-populate both files so the downloader skips HTTP entirely.
    for seg in segments:
        (tmp_path / url_to_filename(seg.url)).write_bytes(b"data")

    result = await download_segments(segments, tmp_path, max_concurrent=2)

    assert len(result) == 2
    assert all(s.downloaded for s in result)
