"""Clean raw Whisper transcripts using Claude.

Design notes
------------
- Sends the full transcript to Claude in a single call.  At typical speaking
  rates (120–180 wpm) a 4-hour Space produces ~40K words ≈ 55K tokens —
  well within Claude's 200K context window.
- For extremely long transcripts (> ~400K chars) the text is split at
  paragraph boundaries and each chunk is cleaned independently before
  being reassembled.
- Uses claude-haiku for speed and cost efficiency; accuracy is sufficient
  for filler-word removal.
- Requires the ``ANTHROPIC_API_KEY`` environment variable.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_CHUNK_CHARS = 400_000  # ~100K tokens — split above this threshold

_PROMPT = """\
You are an expert transcript editor.

Clean the following transcript from a Twitter/X Space audio recording.

Your tasks:
- Remove filler words (um, uh, you know, like, basically, literally, right, \
so yeah, I mean, kind of, sort of, etc.)
- Fix obvious transcription errors (wrong homophones, missing punctuation)
- Improve sentence readability while keeping the original meaning exactly
- Keep ALL [HH:MM:SS] timestamps exactly as they appear
- Do NOT add new content, change facts, or remove speaker turns

Return only the cleaned transcript. No preamble, no commentary.

TRANSCRIPT:
{transcript}"""


def clean_transcript(
    transcript_path: Path,
    model: str = "claude-haiku-4-5-20251001",
) -> Path:
    """Clean *transcript_path* with Claude and return the clean transcript path.

    Args:
        transcript_path: Path to the raw ``*_transcript.txt`` file.
        model:           Claude model ID to use for cleaning.

    Returns:
        Path to the ``*_clean_transcript.txt`` file.

    Raises:
        ImportError:     if ``anthropic`` is not installed.
        EnvironmentError: if ``ANTHROPIC_API_KEY`` is not set.
    """
    try:
        import anthropic
    except ImportError as exc:
        raise ImportError(
            "anthropic is required for transcript cleaning.\n"
            "Install it with:  pip install anthropic"
        ) from exc

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set.\n"
            "Export your Anthropic API key to enable transcript cleaning."
        )

    text = transcript_path.read_text(encoding="utf-8")
    client = anthropic.Anthropic(api_key=api_key)

    if len(text) <= _CHUNK_CHARS:
        cleaned = _clean_chunk(client, model, text)
    else:
        cleaned = _clean_in_chunks(client, model, text)

    # Output name: foo_transcript.txt → foo_clean_transcript.txt
    base = transcript_path.stem.replace("_transcript", "")
    output_path = transcript_path.with_name(base + "_clean_transcript.txt")
    output_path.write_text(cleaned, encoding="utf-8")
    logger.info("Clean transcript saved: %s", output_path.name)
    return output_path


# ── Internal helpers ──────────────────────────────────────────────────────────

def _clean_chunk(client, model: str, text: str) -> str:
    response = client.messages.create(
        model=model,
        max_tokens=8096,
        messages=[{"role": "user", "content": _PROMPT.format(transcript=text)}],
    )
    return response.content[0].text


def _clean_in_chunks(client, model: str, text: str) -> str:
    """Split at paragraph boundaries and clean each chunk independently."""
    paragraphs = text.split("\n\n")
    chunks, current = [], ""
    for para in paragraphs:
        if len(current) + len(para) + 2 > _CHUNK_CHARS:
            if current.strip():
                chunks.append(current.strip())
            current = para
        else:
            current += ("\n\n" if current else "") + para
    if current.strip():
        chunks.append(current.strip())

    logger.info("Cleaning transcript in %d chunk(s)…", len(chunks))
    return "\n\n".join(_clean_chunk(client, model, chunk) for chunk in chunks)
