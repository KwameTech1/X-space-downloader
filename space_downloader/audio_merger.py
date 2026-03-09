"""Audio segment merger using ffmpeg.

Design notes
------------
We use ffmpeg's ``concat`` demuxer (via a text file listing every segment path)
rather than piping raw bytes.  This approach:

* handles thousands of segments without hitting shell argument-length limits;
* avoids re-encoding for ``.aac`` → ``.m4a`` (stream copy);
* supports re-encoding to MP3 or WAV with sane quality defaults.

ffmpeg is treated as an external dependency.  We surface a friendly error if
it is not found on PATH rather than crashing with an ``OSError``.
"""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List

from .exceptions import FFmpegNotFoundError, MergeError
from .models import SegmentInfo

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = ("mp3", "m4a", "wav", "aac")


def check_ffmpeg() -> str:
    """Return the path to ffmpeg, or raise :class:`FFmpegNotFoundError`.

    Called early so the user sees a clear message before any downloading
    starts if ffmpeg is missing.
    """
    path = shutil.which("ffmpeg")
    if not path:
        raise FFmpegNotFoundError(
            "ffmpeg not found on PATH.\n"
            "Install it and make sure it is accessible from your terminal:\n"
            "  Windows : winget install ffmpeg   OR   choco install ffmpeg\n"
            "  macOS   : brew install ffmpeg\n"
            "  Linux   : sudo apt install ffmpeg\n"
            "Then re-run the command."
        )
    return path


def merge_segments(
    segments: List[SegmentInfo],
    output_path: Path,
    output_format: str = "mp3",
    cleanup_segments: bool = True,
) -> Path:
    """Merge downloaded audio segments into a single file.

    Args:
        segments:         Segments to merge, **in playlist order**.
        output_path:      Destination path *without* extension.
                          The correct extension is appended automatically.
        output_format:    One of ``mp3``, ``m4a``, ``wav``, ``aac``.
        cleanup_segments: If ``True``, delete segment files after merging.

    Returns:
        The path to the merged output file.

    Raises:
        :class:`MergeError`: if ffmpeg exits with a non-zero code or produces
            an empty file.
        :class:`FFmpegNotFoundError`: if ffmpeg is not on PATH.
    """
    if output_format not in SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported format {output_format!r}. "
            f"Choose one of: {', '.join(SUPPORTED_FORMATS)}"
        )

    ffmpeg = check_ffmpeg()

    valid = [s for s in segments if s.local_path and s.local_path.exists()]
    if not valid:
        raise MergeError("No valid segment files to merge")

    logger.info("Merging %d segments → .%s …", len(valid), output_format)

    # Write the ffmpeg concat file (one "file '/abs/path'" line per segment).
    concat_file = Path(tempfile.mktemp(suffix=".txt"))
    try:
        with concat_file.open("w", encoding="utf-8") as fh:
            for seg in valid:
                # ffmpeg requires forward slashes even on Windows.
                safe_path = str(seg.local_path.resolve()).replace("\\", "/")
                fh.write(f"file '{safe_path}'\n")

        final = output_path.with_suffix(f".{output_format}")

        cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file)]

        if output_format == "mp3":
            # VBR quality 2 ≈ 170–210 kbps — transparent quality.
            cmd += ["-c:a", "libmp3lame", "-q:a", "2"]
        elif output_format == "m4a":
            cmd += ["-c:a", "aac", "-b:a", "192k"]
        elif output_format == "wav":
            cmd += ["-c:a", "pcm_s16le"]
        elif output_format == "aac":
            # Segments are already AAC; copy without re-encoding.
            cmd += ["-c:a", "copy"]

        cmd += ["-loglevel", "error", str(final)]
        logger.debug("ffmpeg: %s", " ".join(cmd))

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise MergeError(
                f"ffmpeg exited with code {result.returncode}:\n{result.stderr.strip()}"
            )

        if not final.exists() or final.stat().st_size == 0:
            raise MergeError("ffmpeg produced an empty output file")

        size_mb = final.stat().st_size / 1_000_000
        logger.info("Merged output: %s (%.1f MB)", final, size_mb)
        return final

    finally:
        concat_file.unlink(missing_ok=True)

        if cleanup_segments:
            seg_dirs: set[Path] = set()
            for seg in valid:
                if seg.local_path and seg.local_path.exists():
                    seg_dirs.add(seg.local_path.parent)
                    seg.local_path.unlink()
            for d in seg_dirs:
                try:
                    d.rmdir()  # only succeeds if the directory is now empty
                except OSError:
                    pass
