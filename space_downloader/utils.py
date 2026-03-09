"""Utility helpers for X Spaces Downloader."""

import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse

# Matches /spaces/ID or /audio-space/ID in any Twitter/X URL
_SPACE_ID_RE = re.compile(r"(?:spaces|audio-space)/([A-Za-z0-9]+)", re.IGNORECASE)

# Bare Space ID: 10–30 alphanumeric chars
_BARE_ID_RE = re.compile(r"^[A-Za-z0-9]{10,30}$")


def extract_space_id(url: str) -> str:
    """Extract the Space ID from a Twitter/X Space URL.

    Accepts:
        https://x.com/i/spaces/SPACE_ID
        https://twitter.com/i/spaces/SPACE_ID
        https://x.com/i/spaces/SPACE_ID/peek
        SPACE_ID (bare ID)

    Raises:
        ValueError: if no Space ID can be found.
    """
    url = url.strip().rstrip("/")

    match = _SPACE_ID_RE.search(url)
    if match:
        return match.group(1)

    if _BARE_ID_RE.match(url):
        return url

    raise ValueError(
        f"Could not extract Space ID from: {url!r}\n"
        "Expected format: https://x.com/i/spaces/SPACE_ID"
    )


def make_safe_filename(s: str, max_length: int = 100) -> str:
    """Convert an arbitrary string into a safe filesystem filename."""
    # Strip invalid characters
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s)
    # Collapse runs of underscores/spaces
    safe = re.sub(r"[_\s]+", "_", safe).strip("_. ")
    return (safe[:max_length] if safe else "untitled")


def url_to_filename(url: str) -> str:
    """Derive a stable, unique filename from a segment URL."""
    digest = hashlib.md5(url.encode()).hexdigest()[:8]
    ext = Path(urlparse(url).path).suffix or ".ts"
    return f"seg_{digest}{ext}"


def format_bytes(byte_count: int) -> str:
    """Return a human-readable representation of a byte count."""
    for unit in ("B", "KB", "MB", "GB"):
        if byte_count < 1024:
            return f"{byte_count:.1f} {unit}"
        byte_count //= 1024
    return f"{byte_count:.1f} TB"


def format_duration(seconds: float) -> str:
    """Format a duration (seconds) as H:MM:SS or M:SS."""
    total = int(seconds)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def ensure_dir(path: Path) -> Path:
    """Create *path* and all parents; return the path."""
    path.mkdir(parents=True, exist_ok=True)
    return path
