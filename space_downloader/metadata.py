"""Audio metadata tagger using mutagen.

Embeds Space title, host, date, and source URL into the output file.
Supports MP3 (ID3), M4A/AAC (MP4 atoms), and WAV (ID3-in-WAV).

If mutagen is not installed the function emits a warning and returns
without error — metadata is optional and should never break the download.
"""

import logging
from pathlib import Path

from .models import SpaceMetadata

logger = logging.getLogger(__name__)


def tag_audio_file(
    file_path: Path,
    metadata: SpaceMetadata,
    output_format: str,
) -> None:
    """Embed *metadata* into *file_path*.

    Args:
        file_path:     Path to the audio file.
        metadata:      Space metadata to embed.
        output_format: ``mp3``, ``m4a``, ``aac``, or ``wav``.
    """
    try:
        import mutagen  # noqa: F401 — presence check
    except ImportError:
        logger.warning(
            "mutagen is not installed — skipping metadata tagging. "
            "Run: pip install mutagen"
        )
        return

    try:
        if output_format == "mp3":
            _tag_mp3(file_path, metadata)
        elif output_format in ("m4a", "aac"):
            _tag_m4a(file_path, metadata)
        elif output_format == "wav":
            _tag_wav(file_path, metadata)
        else:
            logger.debug("No metadata tagging implemented for format: %s", output_format)
            return

        logger.debug("Metadata tagged: %s", file_path.name)

    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Could not tag audio file: %s", exc)


# ── Format-specific helpers ───────────────────────────────────────────────────

def _tag_mp3(path: Path, meta: SpaceMetadata) -> None:
    from mutagen.id3 import ID3, TIT2, TPE1, TDRC, COMM
    from mutagen.id3 import error as ID3Error

    try:
        tags = ID3(str(path))
    except ID3Error:
        tags = ID3()

    tags["TIT2"] = TIT2(encoding=3, text=meta.title)
    tags["TPE1"] = TPE1(encoding=3, text=meta.host_display_name)
    tags["COMM"] = COMM(encoding=3, lang="eng", desc="", text=meta.original_url)

    if meta.started_at:
        tags["TDRC"] = TDRC(encoding=3, text=meta.started_at.strftime("%Y-%m-%d"))

    tags.save(str(path))


def _tag_m4a(path: Path, meta: SpaceMetadata) -> None:
    from mutagen.mp4 import MP4

    tags = MP4(str(path))
    tags["\xa9nam"] = [meta.title]            # title
    tags["\xa9ART"] = [meta.host_display_name] # artist
    tags["\xa9cmt"] = [meta.original_url]      # comment / source URL

    if meta.started_at:
        tags["\xa9day"] = [meta.started_at.strftime("%Y-%m-%d")]

    tags.save()


def _tag_wav(path: Path, meta: SpaceMetadata) -> None:
    from mutagen.wave import WAVE
    from mutagen.id3 import TIT2, TPE1, COMM

    tags = WAVE(str(path))
    if tags.tags is None:
        tags.add_tags()

    tags["TIT2"] = TIT2(encoding=3, text=meta.title)
    tags["TPE1"] = TPE1(encoding=3, text=meta.host_display_name)
    tags["COMM"] = COMM(encoding=3, lang="eng", desc="", text=meta.original_url)
    tags.save()
