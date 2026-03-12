"""Audio transcription using faster-whisper (local, no API key needed).

Design notes
------------
- Uses ``faster-whisper`` which runs CTranslate2-optimised Whisper models
  locally — audio never leaves the machine.
- Models are downloaded once to the HuggingFace cache on first use.
- VAD filtering skips silent regions, speeding up long recordings.
- Output is written incrementally so a crash mid-way still leaves a
  usable partial transcript.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

VALID_MODELS = ("tiny", "base", "small", "medium", "large-v2", "large-v3")
DEFAULT_MODEL = "small"


def _fmt_ts(seconds: float) -> str:
    """Convert float seconds → HH:MM:SS string."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def transcribe_audio(
    audio_path: Path,
    model_size: str = DEFAULT_MODEL,
    language: Optional[str] = None,
    device: str = "cpu",
) -> Path:
    """Transcribe *audio_path* with Whisper and return the transcript file path.

    Args:
        audio_path:  Path to the merged audio file (mp3 / m4a / wav / aac).
        model_size:  Whisper model variant.  Larger = more accurate, slower.
                     ``small`` is a good default: fast on CPU, ~94% accuracy.
        language:    ISO-639-1 language code (e.g. ``"en"``).
                     Auto-detected when ``None``.
        device:      ``"cpu"`` or ``"cuda"``.

    Returns:
        Path to the ``{stem}_transcript.txt`` file.

    Raises:
        ImportError:       if ``faster-whisper`` is not installed.
        FileNotFoundError: if *audio_path* does not exist.
        ValueError:        if *model_size* is not a recognised variant.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise ImportError(
            "faster-whisper is required for transcription.\n"
            "Install it with:  pip install faster-whisper"
        ) from exc

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    if model_size not in VALID_MODELS:
        raise ValueError(
            f"Invalid model {model_size!r}. "
            f"Choose one of: {', '.join(VALID_MODELS)}"
        )

    compute_type = "int8" if device == "cpu" else "float16"
    logger.info("Loading Whisper '%s' on %s (compute=%s)…", model_size, device, compute_type)
    model = WhisperModel(model_size, device=device, compute_type=compute_type)

    logger.info("Transcribing %s…", audio_path.name)
    segments, info = model.transcribe(
        str(audio_path),
        language=language,
        beam_size=5,
        word_timestamps=False,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )

    logger.info(
        "Detected language: %s (confidence %.0f%%)",
        info.language,
        info.language_probability * 100,
    )

    output_path = audio_path.with_name(audio_path.stem + "_transcript.txt")
    count = 0

    with output_path.open("w", encoding="utf-8") as fh:
        fh.write(f"# Transcript\n")
        fh.write(f"# Source  : {audio_path.name}\n")
        fh.write(f"# Language: {info.language}\n")
        fh.write(f"# Model   : whisper-{model_size}\n\n")

        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue
            fh.write(f"[{_fmt_ts(seg.start)}]\n{text}\n\n")
            fh.flush()
            count += 1

    logger.info("Transcription complete: %d segments → %s", count, output_path.name)
    return output_path
