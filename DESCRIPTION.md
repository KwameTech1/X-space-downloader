 {
    slug: 'x-spaces-downloader',
    title: 'X Spaces Downloader',
    description: 'A full-stack tool to download, transcribe, and summarise Twitter/X Space recordings.',
    longDescription: `A production-quality Python tool that downloads Twitter/X Space audio replays, transcribes them with Whisper, cleans the transcript, and generates an article-ready summary with Claude AI.

## What it does

- Accepts any Twitter/X Space URL and downloads the full audio as an MP3
- Fetches Space metadata (title, host, duration) via Twitter's private GraphQL API
- Parses the HLS playlist and downloads thousands of AAC segments in parallel with retry and resume support
- Merges segments with ffmpeg, skipping any corrupt source data automatically
- Optionally transcribes the audio locally using OpenAI Whisper (via faster-whisper) — no API key needed
- Cleans the raw transcript (removes filler words, fixes errors) using Claude Haiku
- Generates a structured article-ready summary — title, key topics, insights, notable quotes — using Claude Sonnet
- Ships a FastAPI web UI with real-time WebSocket progress, a Whisper model selector, and progressive download buttons for each output file

## Tech stack

- Python 3.13, asyncio, aiohttp
- ffmpeg (audio merging via concat demuxer)
- faster-whisper / OpenAI Whisper (local transcription)
- Anthropic Claude API (transcript cleaning + summarisation)
- FastAPI + uvicorn + WebSockets (web UI)
- Rich + Typer (CLI interface)
- m3u8, mutagen

## Key learnings

- Reverse-engineered Twitter's rotating GraphQL query IDs and webpack chunk-map discovery to locate AudioSpaceById endpoints without authentication
- Handled real-world HLS stream quirks: ~0.7% of segments served by Twitter's CDN contain corrupt AAC data — solved with per-segment ffmpeg pre-validation
- Bridged async FastAPI with blocking ffmpeg/Whisper calls using run_in_executor so the server stays responsive during long merges and transcriptions
- Streamed live pipeline progress (metadata → download → merge → transcribe → summarise) to the browser via asyncio.Queue-backed WebSockets`,
    tags: ['Python', 'FastAPI', 'CLI', 'AI', 'Whisper', 'Claude', 'HLS', 'ffmpeg', 'WebSockets'],
    github: 'https://github.com/KwameTech1/X-space-downloader',
    live: null,
  },
