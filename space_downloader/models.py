"""Data models for X Spaces Downloader."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class SpaceMetadata:
    """Metadata for a Twitter/X Space."""

    space_id: str
    title: str
    host_username: str
    host_display_name: str
    state: str
    media_key: str
    original_url: str
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    participant_count: int = 0
    stream_url: Optional[str] = None

    @property
    def is_ended(self) -> bool:
        return self.state.lower() in ("ended", "timedout")

    @property
    def is_live(self) -> bool:
        return self.state.lower() == "running"

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.started_at and self.ended_at:
            return (self.ended_at - self.started_at).total_seconds()
        return None


@dataclass
class SegmentInfo:
    """Represents a single audio segment in an HLS stream."""

    url: str
    index: int
    duration: float
    local_path: Optional[Path] = None
    downloaded: bool = False
    download_attempts: int = 0
