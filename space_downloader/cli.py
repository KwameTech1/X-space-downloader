"""CLI entry point for X Spaces Downloader.

Commands
--------
download      Download a Space as an audio file.
info          Show Space metadata without downloading.
list-segments List all HLS segments for a Space.

Built with Typer (argument parsing) and Rich (terminal UI).
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

import aiohttp
import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table

from . import __version__
from .audio_merger import check_ffmpeg, merge_segments
from .exceptions import (
    AuthenticationError,
    ReplayUnavailableError,
    SpaceDownloaderError,
    SpaceLiveError,
    SpaceNotFoundError,
)
from .hls_parser import get_all_segments, total_duration
from .metadata import tag_audio_file
from .models import SpaceMetadata
from .segment_downloader import download_segments
from .twitter_api import TwitterAPIClient
from .utils import extract_space_id, format_duration, make_safe_filename

# ── App setup ─────────────────────────────────────────────────────────────────

app = typer.Typer(
    name="space-downloader",
    help="[bold cyan]X Spaces Downloader[/bold cyan] — download Twitter/X Space audio.",
    rich_markup_mode="rich",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()
err_console = Console(stderr=True, style="bold red")


# ── Shared options ─────────────────────────────────────────────────────────────

def _auth_options(f):
    """Decorator that adds shared --auth-token / --ct0 options."""
    import functools

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        return f(*args, **kwargs)

    return wrapper


# ── Callbacks ─────────────────────────────────────────────────────────────────

def _version_cb(value: bool) -> None:
    if value:
        console.print(
            f"[bold]space-downloader[/bold] [cyan]{__version__}[/cyan]"
        )
        raise typer.Exit()


@app.callback()
def _global(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        callback=_version_cb,
        is_eager=True,
        help="Print version and exit.",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-V", help="Enable debug logging."
    ),
) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s  %(name)s: %(message)s")


# ── download command ───────────────────────────────────────────────────────────

@app.command()
def download(
    url: str = typer.Argument(..., help="Twitter/X Space URL or Space ID"),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path without extension (default: derived from title).",
    ),
    format: str = typer.Option(
        "mp3",
        "--format",
        "-f",
        help="Output format: mp3 | m4a | wav | aac",
    ),
    auth_token: Optional[str] = typer.Option(
        None,
        "--auth-token",
        envvar="TWITTER_AUTH_TOKEN",
        help="Your Twitter auth_token cookie (required for some replays).",
    ),
    ct0: Optional[str] = typer.Option(
        None,
        "--ct0",
        envvar="TWITTER_CT0",
        help="Your Twitter ct0 cookie (CSRF token — required alongside --auth-token).",
    ),
    concurrency: int = typer.Option(
        8,
        "--concurrency",
        "-c",
        min=1,
        max=32,
        help="Parallel segment download connections.",
    ),
    keep_segments: bool = typer.Option(
        False,
        "--keep-segments",
        help="Keep raw .aac segment files after merging.",
    ),
    temp_dir: Optional[Path] = typer.Option(
        None,
        "--temp-dir",
        help="Directory for temporary segment files (default: beside output file).",
    ),
) -> None:
    """Download a Twitter/X Space as an audio file.

    \b
    Examples:
      space-downloader download https://x.com/i/spaces/1LyxBxyzABC
      space-downloader download https://x.com/i/spaces/1LyxBxyzABC --format m4a
      space-downloader download https://x.com/i/spaces/1LyxBxyzABC \\
          --auth-token abc123 --ct0 xyz456
    """
    try:
        asyncio.run(
            _run_download(
                url=url,
                output=output,
                fmt=format.lower(),
                auth_token=auth_token,
                ct0=ct0,
                concurrency=concurrency,
                keep_segments=keep_segments,
                temp_dir=temp_dir,
            )
        )
    except SpaceDownloaderError as exc:
        err_console.print(f"\nError: {exc}")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled.[/yellow]")
        raise typer.Exit(130)


async def _run_download(
    url: str,
    output: Optional[Path],
    fmt: str,
    auth_token: Optional[str],
    ct0: Optional[str],
    concurrency: int,
    keep_segments: bool,
    temp_dir: Optional[Path],
) -> None:
    _print_banner()

    # ── 1. Parse URL ──────────────────────────────────────────────────────────
    space_id = extract_space_id(url)
    console.print(f"  [dim]Space ID:[/dim] [bold]{space_id}[/bold]\n")

    # ── 2. Fetch metadata ─────────────────────────────────────────────────────
    async with TwitterAPIClient(auth_token=auth_token, ct0=ct0) as client:
        with console.status("[bold green]Fetching Space metadata…"):
            metadata = await client.get_space_metadata(space_id)

        _print_metadata(metadata)

        if metadata.is_live:
            raise SpaceLiveError(
                "This Space is currently live. "
                "Wait until it ends before downloading the replay."
            )

        # ── 3. Locate HLS stream ──────────────────────────────────────────────
        with console.status("[bold green]Locating HLS stream…"):
            stream_url = await client.get_stream_url(metadata.media_key)

    console.print("[green]✓[/green]  HLS stream located\n")

    # ── 4. Parse playlist ─────────────────────────────────────────────────────
    async with aiohttp.ClientSession() as session:
        with console.status("[bold green]Parsing playlist…"):
            segments = await get_all_segments(session, stream_url)

    dur = total_duration(segments)
    console.print(
        f"[green]✓[/green]  [bold]{len(segments)}[/bold] segments found "
        f"([dim]~{format_duration(dur)}[/dim])\n"
    )

    # ── 5. Choose output path ─────────────────────────────────────────────────
    if output is None:
        safe_title = make_safe_filename(metadata.title or f"space_{space_id}")
        output = Path(safe_title)

    seg_dir = (temp_dir or output.parent or Path(".")) / f".segments_{space_id}"

    # ── 6. Download segments ──────────────────────────────────────────────────
    console.print()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Downloading segments…", total=len(segments))
        downloaded = await download_segments(
            segments=segments,
            output_dir=seg_dir,
            max_concurrent=concurrency,
            progress=progress,
            overall_task=task,
        )

    console.print(
        f"\n[green]✓[/green]  {len(downloaded)}/{len(segments)} segments downloaded\n"
    )

    # ── 7. Merge ──────────────────────────────────────────────────────────────
    with console.status(f"[bold green]Merging → .{fmt}…"):
        check_ffmpeg()
        final = merge_segments(
            segments=downloaded,
            output_path=output,
            output_format=fmt,
            cleanup_segments=not keep_segments,
        )

    console.print(f"[green]✓[/green]  Merged: [bold]{final}[/bold]\n")

    # ── 8. Tag metadata ───────────────────────────────────────────────────────
    with console.status("[bold green]Embedding metadata…"):
        tag_audio_file(final, metadata, fmt)

    console.print("[green]✓[/green]  Metadata embedded\n")

    # ── Summary ───────────────────────────────────────────────────────────────
    size_mb = final.stat().st_size / 1_000_000
    console.print(
        Panel.fit(
            f"[bold green]Done![/bold green]\n"
            f"[dim]File :[/dim] [cyan]{final}[/cyan]\n"
            f"[dim]Size :[/dim] {size_mb:.1f} MB",
            border_style="green",
        )
    )


# ── info command ──────────────────────────────────────────────────────────────

@app.command()
def info(
    url: str = typer.Argument(..., help="Twitter/X Space URL or Space ID"),
    auth_token: Optional[str] = typer.Option(
        None, "--auth-token", envvar="TWITTER_AUTH_TOKEN"
    ),
    ct0: Optional[str] = typer.Option(None, "--ct0", envvar="TWITTER_CT0"),
) -> None:
    """Show metadata for a Space without downloading it."""
    try:
        asyncio.run(_run_info(url, auth_token, ct0))
    except SpaceDownloaderError as exc:
        err_console.print(f"\nError: {exc}")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        raise typer.Exit(130)


async def _run_info(url: str, auth_token: Optional[str], ct0: Optional[str]) -> None:
    space_id = extract_space_id(url)
    async with TwitterAPIClient(auth_token=auth_token, ct0=ct0) as client:
        with console.status("[bold green]Fetching metadata…"):
            metadata = await client.get_space_metadata(space_id)
    _print_metadata(metadata)


# ── list-segments command ──────────────────────────────────────────────────────

@app.command(name="list-segments")
def list_segments(
    url: str = typer.Argument(..., help="Twitter/X Space URL or Space ID"),
    auth_token: Optional[str] = typer.Option(
        None, "--auth-token", envvar="TWITTER_AUTH_TOKEN"
    ),
    ct0: Optional[str] = typer.Option(None, "--ct0", envvar="TWITTER_CT0"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max segments to display."),
) -> None:
    """List HLS segments for a Space."""
    try:
        asyncio.run(_run_list_segments(url, auth_token, ct0, limit))
    except SpaceDownloaderError as exc:
        err_console.print(f"\nError: {exc}")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        raise typer.Exit(130)


async def _run_list_segments(
    url: str, auth_token: Optional[str], ct0: Optional[str], limit: int
) -> None:
    space_id = extract_space_id(url)

    async with TwitterAPIClient(auth_token=auth_token, ct0=ct0) as client:
        with console.status("[bold green]Fetching metadata…"):
            metadata = await client.get_space_metadata(space_id)
        with console.status("[bold green]Locating stream…"):
            stream_url = await client.get_stream_url(metadata.media_key)

    async with aiohttp.ClientSession() as session:
        with console.status("[bold green]Parsing playlist…"):
            segments = await get_all_segments(session, stream_url)

    table = Table(title=f"Segments — {space_id}", show_lines=False)
    table.add_column("#", justify="right", style="dim", width=6)
    table.add_column("Duration", justify="right", width=10)
    table.add_column("URL", overflow="fold")

    for seg in segments[:limit]:
        table.add_row(str(seg.index), f"{seg.duration:.1f}s", seg.url)

    if len(segments) > limit:
        table.add_row("…", "…", f"({len(segments) - limit} more segments)")

    console.print(table)
    dur = total_duration(segments)
    console.print(
        f"\nTotal: [bold]{len(segments)}[/bold] segments, "
        f"~[bold]{format_duration(dur)}[/bold]"
    )


# ── UI helpers ────────────────────────────────────────────────────────────────

def _print_banner() -> None:
    console.print(
        Panel.fit(
            f"[bold cyan]X Spaces Downloader[/bold cyan]  [dim]v{__version__}[/dim]",
            border_style="cyan",
        )
    )
    console.print()


def _print_metadata(meta: SpaceMetadata) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim", width=12)
    table.add_column()

    table.add_row("Title", f"[bold]{meta.title}[/bold]")
    table.add_row(
        "Host", f"[cyan]@{meta.host_username}[/cyan] ({meta.host_display_name})"
    )
    table.add_row("State", _state_badge(meta.state))

    if meta.started_at:
        table.add_row("Started", meta.started_at.strftime("%Y-%m-%d %H:%M UTC"))
    if meta.ended_at:
        table.add_row("Ended", meta.ended_at.strftime("%Y-%m-%d %H:%M UTC"))
    if meta.duration_seconds:
        table.add_row("Duration", format_duration(meta.duration_seconds))

    table.add_row("Space ID", meta.space_id)

    console.print(Panel(table, title="[bold]Space Metadata[/bold]", border_style="blue"))
    console.print()


def _state_badge(state: str) -> str:
    s = state.lower()
    if s == "running":
        return "[bold red]● LIVE[/bold red]"
    if s in ("ended", "timedout"):
        return "[bold green]● Ended[/bold green]"
    return f"[yellow]{state}[/yellow]"


# ── Entry point ───────────────────────────────────────────────────────────────

def run() -> None:
    """Installed entry point (``space-downloader``)."""
    app()
