"""Custom exceptions for X Spaces Downloader."""


class SpaceDownloaderError(Exception):
    """Base exception for all downloader errors."""


class SpaceNotFoundError(SpaceDownloaderError):
    """Raised when a Space cannot be found."""


class SpaceLiveError(SpaceDownloaderError):
    """Raised when attempting to download a currently live Space."""


class ReplayUnavailableError(SpaceDownloaderError):
    """Raised when the replay is not available for download."""


class AuthenticationError(SpaceDownloaderError):
    """Raised when authentication fails or credentials are missing."""


class APIError(SpaceDownloaderError):
    """Raised when an API call fails unexpectedly."""


class SegmentDownloadError(SpaceDownloaderError):
    """Raised when too many segment downloads fail."""


class FFmpegNotFoundError(SpaceDownloaderError):
    """Raised when ffmpeg is not installed or not on PATH."""


class MergeError(SpaceDownloaderError):
    """Raised when audio segment merging fails."""
