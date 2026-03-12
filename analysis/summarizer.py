"""Generate a structured, article-ready summary from a Space transcript.

Design notes
------------
- Passes the full clean transcript to Claude Sonnet in a single call.
  A 4-hour Space fits comfortably within the 200K-token context window.
- The output is formatted with named sections (TITLE, SUMMARY, KEY TOPICS,
  KEY INSIGHTS, NOTABLE QUOTES) so it is immediately usable for article
  or blog writing.
- Space metadata (title, host, URL) is injected as context so Claude can
  produce a more relevant headline and summary.
- Requires the ``ANTHROPIC_API_KEY`` environment variable.
"""

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_PROMPT = """\
You are an expert content strategist and journalist specialising in \
technology and developer community content.

Generate a structured summary from the Twitter/X Space transcript below. \
The output will be used directly for article writing and content creation.

{context}\
Format your response EXACTLY as shown (keep the section headings):

TITLE:
[A compelling, specific article headline that captures the main theme]

SUMMARY:
[2–3 paragraphs giving a clear, engaging overview of the full discussion. \
Write in third person, present tense.]

KEY TOPICS:
- [Topic 1]
- [Topic 2]
- [Topic 3]
- [Add more as needed]

KEY INSIGHTS:
- [Concrete insight 1]
- [Concrete insight 2]
- [Concrete insight 3]
- [Add more as needed]

NOTABLE QUOTES:
"[Direct quote from the transcript — copy verbatim]"
"[Another notable quote]"

---

TRANSCRIPT:
{transcript}"""


def summarize_transcript(
    transcript_path: Path,
    metadata=None,
    model: str = "claude-sonnet-4-6",
) -> Path:
    """Summarise *transcript_path* with Claude and return the summary file path.

    Args:
        transcript_path: Path to the clean transcript (``*_clean_transcript.txt``
                         or raw ``*_transcript.txt`` if cleaning was skipped).
        metadata:        Optional :class:`SpaceMetadata` for richer context.
        model:           Claude model ID.

    Returns:
        Path to the ``*_summary.txt`` file.

    Raises:
        ImportError:      if ``anthropic`` is not installed.
        EnvironmentError: if ``ANTHROPIC_API_KEY`` is not set.
    """
    try:
        import anthropic
    except ImportError as exc:
        raise ImportError(
            "anthropic is required for summarization.\n"
            "Install it with:  pip install anthropic"
        ) from exc

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set.\n"
            "Export your Anthropic API key to enable summarization."
        )

    text = transcript_path.read_text(encoding="utf-8")
    client = anthropic.Anthropic(api_key=api_key)

    context = ""
    if metadata:
        context = (
            f"Space Title : {metadata.title}\n"
            f"Host        : @{metadata.host_username} ({metadata.host_display_name})\n"
            f"Space URL   : {metadata.original_url}\n\n"
        )

    response = client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": _PROMPT.format(context=context, transcript=text),
        }],
    )

    summary = response.content[0].text

    # Derive base name: strip any _clean_transcript or _transcript suffix
    base = transcript_path.stem
    for suffix in ("_clean_transcript", "_transcript"):
        base = base.replace(suffix, "")
    output_path = transcript_path.with_name(base + "_summary.txt")
    output_path.write_text(summary, encoding="utf-8")
    logger.info("Summary saved: %s", output_path.name)
    return output_path
