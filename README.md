# X Spaces Downloader

A professional, reliable command-line tool for downloading Twitter/X Spaces audio.

## Features

- **Async parallel downloads** — handles thousands of HLS segments efficiently
- **Auto-resume** — skips already-downloaded segments on retry
- **Multiple output formats** — MP3, M4A, WAV, AAC
- **Metadata tagging** — embeds title, host, date, and source URL
- **Beautiful CLI** — Rich progress bars, speed, ETA
- **Cross-platform** — Windows, macOS, Linux

## Requirements

- Python 3.9+
- [ffmpeg](https://ffmpeg.org/download.html) on your PATH

## Installation

```bash
# From PyPI (once published)
pip install space-downloader

# From source
git clone https://github.com/youruser/x-space-downloader
cd x-space-downloader
pip install -r requirements.txt
pip install -e .
```

## Usage

### Download a Space

```bash
space-downloader download https://x.com/i/spaces/1LyxBxyzABC
```

### Download as M4A

```bash
space-downloader download https://x.com/i/spaces/1LyxBxyzABC --format m4a
```

### Custom output filename

```bash
space-downloader download https://x.com/i/spaces/1LyxBxyzABC --output my_space
# → my_space.mp3
```

### Show Space metadata without downloading

```bash
space-downloader info https://x.com/i/spaces/1LyxBxyzABC
```

### List all HLS segments

```bash
space-downloader list-segments https://x.com/i/spaces/1LyxBxyzABC
```

## Authentication

Most public, ended Spaces work without any credentials. If you get a 401 error,
the Space requires a logged-in session.

1. Log in to [x.com](https://x.com) in your browser.
2. Open DevTools → Application → Cookies → `https://x.com`.
3. Copy the values of `auth_token` and `ct0`.

```bash
space-downloader download URL \
  --auth-token YOUR_AUTH_TOKEN \
  --ct0 YOUR_CT0

# Or set environment variables (recommended):
export TWITTER_AUTH_TOKEN=your_auth_token
export TWITTER_CT0=your_ct0
space-downloader download URL
```

## Options

| Option | Default | Description |
|---|---|---|
| `--format` / `-f` | `mp3` | Output format: `mp3`, `m4a`, `wav`, `aac` |
| `--output` / `-o` | (from title) | Output file path (no extension) |
| `--concurrency` / `-c` | `8` | Parallel download connections |
| `--keep-segments` | off | Keep raw segment files after merging |
| `--temp-dir` | (beside output) | Directory for temporary files |
| `--auth-token` | — | Twitter `auth_token` cookie |
| `--ct0` | — | Twitter `ct0` CSRF cookie |
| `--verbose` / `-V` | off | Enable debug logging |

## Project Structure

```
space_downloader/
├── cli.py                # Typer CLI — download, info, list-segments
├── twitter_api.py        # GraphQL + REST API client
├── hls_parser.py         # M3U8 playlist parser
├── segment_downloader.py # Async parallel downloader with retry
├── audio_merger.py       # ffmpeg concat merge
├── metadata.py           # mutagen metadata tagging
├── models.py             # SpaceMetadata, SegmentInfo dataclasses
├── utils.py              # URL parsing, formatting helpers
└── exceptions.py         # Custom exception hierarchy
```

## Running Tests

```bash
pip install pytest pytest-asyncio
pytest tests/ -v
```

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `ffmpeg not found` | ffmpeg not installed | Install ffmpeg and add to PATH |
| `401 Unauthorized` | Space needs login | Provide `--auth-token` / `--ct0` |
| `404 Not Found` | Space doesn't exist or expired | Check the URL |
| `Replay unavailable` | Host disabled replays | Nothing can be done |
| `Space is live` | Space still running | Wait for it to end |
