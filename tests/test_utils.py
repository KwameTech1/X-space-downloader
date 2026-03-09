"""Tests for space_downloader.utils."""

import pytest
from space_downloader.utils import (
    extract_space_id,
    format_bytes,
    format_duration,
    make_safe_filename,
    url_to_filename,
)


class TestExtractSpaceId:
    def test_x_url(self):
        assert extract_space_id("https://x.com/i/spaces/1LyxBxyzABC") == "1LyxBxyzABC"

    def test_twitter_url(self):
        assert (
            extract_space_id("https://twitter.com/i/spaces/1LyxBxyzABC")
            == "1LyxBxyzABC"
        )

    def test_url_with_peek_suffix(self):
        assert (
            extract_space_id("https://x.com/i/spaces/1LyxBxyzABC/peek")
            == "1LyxBxyzABC"
        )

    def test_url_with_trailing_slash(self):
        assert (
            extract_space_id("https://x.com/i/spaces/1LyxBxyzABC/")
            == "1LyxBxyzABC"
        )

    def test_bare_id(self):
        assert extract_space_id("1LyxBxyzABCDEF") == "1LyxBxyzABCDEF"

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Could not extract"):
            extract_space_id("https://x.com/someone")

    def test_strips_whitespace(self):
        assert extract_space_id("  https://x.com/i/spaces/1LyxBxyzABC  ") == "1LyxBxyzABC"


class TestMakeSafeFilename:
    def test_basic(self):
        assert make_safe_filename("Hello World") == "Hello_World"

    def test_removes_forbidden_chars(self):
        result = make_safe_filename('File: <Name>/Test?')
        for ch in '<>:"/\\|?*':
            assert ch not in result

    def test_max_length(self):
        result = make_safe_filename("a" * 200, max_length=50)
        assert len(result) <= 50

    def test_empty_input_returns_untitled(self):
        assert make_safe_filename("...") == "untitled"

    def test_collapses_spaces(self):
        assert "_" * 2 not in make_safe_filename("Hello   World")


class TestFormatDuration:
    def test_seconds_only(self):
        assert format_duration(65) == "1:05"

    def test_hours(self):
        assert format_duration(3661) == "1:01:01"

    def test_zero(self):
        assert format_duration(0) == "0:00"

    def test_exactly_one_hour(self):
        assert format_duration(3600) == "1:00:00"


class TestFormatBytes:
    def test_bytes(self):
        assert "B" in format_bytes(512)

    def test_kilobytes(self):
        assert "KB" in format_bytes(1024)

    def test_megabytes(self):
        assert "MB" in format_bytes(2_000_000)


class TestUrlToFilename:
    def test_deterministic(self):
        url = "https://example.com/seg001.aac"
        assert url_to_filename(url) == url_to_filename(url)

    def test_different_urls_differ(self):
        a = url_to_filename("https://example.com/seg001.aac")
        b = url_to_filename("https://example.com/seg002.aac")
        assert a != b

    def test_preserves_extension(self):
        name = url_to_filename("https://example.com/chunk.aac")
        assert name.endswith(".aac")

    def test_fallback_extension(self):
        name = url_to_filename("https://example.com/chunk")
        assert name.endswith(".ts")
