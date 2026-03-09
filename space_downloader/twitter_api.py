"""Twitter/X API client for fetching Space metadata and stream URLs.

Design notes
------------
Twitter does not offer a public API for Spaces. We use the same private GraphQL
and REST endpoints the web client uses, authenticated either with a *guest token*
(works for public, ended Spaces) or the user's own ``auth_token`` + ``ct0``
browser cookies (required for some restricted replays).

The GraphQL query ID for ``AudioSpaceById`` changes over time when Twitter
redeploys. We try several known IDs in order and fall through gracefully.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import quote_plus

import aiohttp

from .exceptions import (
    APIError,
    AuthenticationError,
    ReplayUnavailableError,
    SpaceNotFoundError,
)
from .models import SpaceMetadata

logger = logging.getLogger(__name__)

# ── Auth ──────────────────────────────────────────────────────────────────────

# Twitter's own web-client bearer token — publicly embedded in their JS bundles.
# This is NOT a secret; it is the same token used by every browser session.
TWITTER_BEARER = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

# Known AudioSpaceById query IDs, newest first.
# If one returns HTTP 400 we try the next.
_QUERY_IDS = [
    "xVEzTKg_bSgAiTzHnCDdFA",
    "Bkfch2IGGD8GumXFV-y5FQ",
    "HPEisOmj1epUNLCWTYhNWw",
    "UzmZkgikgjxKWnz9W7xt5g",
    "9HrKcMc_3mh-bEHJdUbhFQ",
]

# Feature flags required by AudioSpaceById
_FEATURES: Dict[str, bool] = {
    "spaces_2022_h2_spaces_communities": True,
    "spaces_2022_h2_clipping": True,
    "spaces_2022_h2_audio_spaces": True,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "tweetypie_unmention_optimization_enabled": True,
    "vibe_api_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": False,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": False,
    "interactive_text_enabled": True,
    "responsive_web_text_conversations_enabled": False,
    "responsive_web_twitter_blue_verified_badge_is_enabled": True,
    "longform_notetweets_richtext_consumption_enabled": False,
}

_GRAPHQL_VARS = {
    "isMetatagsQuery": False,
    "withSuperFollowsUserFields": True,
    "withDownvotePerspective": False,
    "withReactionsMetadata": False,
    "withReactionsPerspective": False,
    "withSuperFollowsTweetFields": True,
    "withReplays": True,
    "withScheduledSpaces": True,
}

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


class TwitterAPIClient:
    """Async context-manager client for Twitter/X private API calls.

    Usage::

        async with TwitterAPIClient(auth_token="...") as client:
            meta = await client.get_space_metadata("1LyxBxyzABC")
            stream_url = await client.get_stream_url(meta.media_key)
    """

    def __init__(
        self,
        auth_token: Optional[str] = None,
        ct0: Optional[str] = None,
    ) -> None:
        self._auth_token = auth_token
        self._ct0 = ct0
        self._guest_token: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None

    # ── Context manager ───────────────────────────────────────────────────────

    async def __aenter__(self) -> "TwitterAPIClient":
        self._session = aiohttp.ClientSession(
            headers={"User-Agent": _USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=30, connect=10),
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._session:
            await self._session.close()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _base_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {TWITTER_BEARER}",
            "Content-Type": "application/json",
            "x-twitter-client-language": "en",
            "x-twitter-active-user": "yes",
        }

    def _auth_headers(self) -> Dict[str, str]:
        headers = self._base_headers()
        if self._ct0:
            headers["x-csrf-token"] = self._ct0
        return headers

    def _auth_cookies(self) -> Dict[str, str]:
        cookies: Dict[str, str] = {}
        if self._auth_token:
            cookies["auth_token"] = self._auth_token
        if self._ct0:
            cookies["ct0"] = self._ct0
        return cookies

    async def _ensure_guest_token(self) -> None:
        """Fetch a guest token if we don't already have one."""
        if self._guest_token:
            return
        assert self._session is not None

        resp = await self._session.post(
            "https://api.twitter.com/1.1/guest/activate.json",
            headers={"Authorization": f"Bearer {TWITTER_BEARER}"},
        )
        if resp.status != 200:
            raise AuthenticationError(
                f"Could not obtain guest token (HTTP {resp.status}). "
                "Twitter may be rate-limiting. Try again later or supply --auth-token."
            )
        data = await resp.json()
        self._guest_token = data["guest_token"]
        logger.debug("Obtained guest token: %s…", self._guest_token[:6])

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_space_metadata(self, space_id: str) -> SpaceMetadata:
        """Fetch and return metadata for *space_id*.

        Tries every known GraphQL query ID until one succeeds.
        Falls back to authenticated requests if a guest token is rejected.
        """
        assert self._session is not None
        use_auth = bool(self._auth_token)

        if not use_auth:
            await self._ensure_guest_token()

        variables = json.dumps({**_GRAPHQL_VARS, "id": space_id})
        features = json.dumps(_FEATURES)

        last_error: Exception = APIError("No query IDs available")

        for qid in _QUERY_IDS:
            url = (
                f"https://twitter.com/i/api/graphql/{qid}/AudioSpaceById"
                f"?variables={quote_plus(variables)}&features={quote_plus(features)}"
            )

            if use_auth:
                headers = self._auth_headers()
                cookies = self._auth_cookies()
            else:
                headers = {**self._base_headers(), "x-guest-token": self._guest_token or ""}
                cookies = {}

            try:
                resp = await self._session.get(url, headers=headers, cookies=cookies)
            except aiohttp.ClientError as exc:
                last_error = APIError(f"Network error: {exc}")
                continue

            logger.debug("Query ID %s → HTTP %s", qid, resp.status)

            if resp.status in (400, 404):
                # 400 = outdated query ID; 404 can also mean query ID not found.
                # Try the next one before giving up.
                last_error = APIError(f"Query ID {qid!r} rejected (HTTP {resp.status})")
                continue

            if resp.status == 401:
                raise AuthenticationError(
                    "Twitter returned 401 Unauthorized.\n"
                    "This Space may require login. Supply your auth token:\n"
                    "  --auth-token YOUR_AUTH_TOKEN  (or set TWITTER_AUTH_TOKEN env var)\n"
                    "  --ct0 YOUR_CT0_TOKEN          (or set TWITTER_CT0 env var)\n"
                    "See README for instructions on obtaining these values."
                )

            if resp.status == 403:
                raise AuthenticationError(
                    "Twitter returned 403 Forbidden.\n"
                    "This Space requires a logged-in account. Supply your auth token:\n"
                    "  --auth-token YOUR_AUTH_TOKEN  (or set TWITTER_AUTH_TOKEN env var)\n"
                    "  --ct0 YOUR_CT0_TOKEN          (or set TWITTER_CT0 env var)"
                )

            if resp.status != 200:
                last_error = APIError(f"HTTP {resp.status} for query ID {qid!r}")
                continue

            data = await resp.json()

            if "errors" in data and data["errors"]:
                msgs = "; ".join(e.get("message", "unknown") for e in data["errors"])
                # Access-control errors mean auth is required, not a bad query ID.
                if any(
                    kw in msgs.lower()
                    for kw in ("authorization", "forbidden", "permission", "not authorized")
                ):
                    raise AuthenticationError(
                        f"Twitter denied access: {msgs}\n"
                        "This Space may require a logged-in account.\n"
                        "Supply --auth-token and --ct0 (see README)."
                    )
                last_error = APIError(f"GraphQL errors: {msgs}")
                continue

            try:
                return self._parse_metadata(data, space_id)
            except (KeyError, TypeError, ValueError) as exc:
                last_error = APIError(f"Failed to parse response: {exc}")
                continue

        # All query IDs exhausted. Distinguish between "Space not found" and
        # "all endpoints rejected" so the user gets a useful error message.
        if all(
            "rejected" in str(last_error) or "HTTP 404" in str(last_error)
            for _ in [1]  # single-iteration trick to keep the check inline
        ):
            raise SpaceNotFoundError(
                f"Space {space_id!r} not found or not accessible without login.\n"
                "If this Space exists and is public, Twitter may have changed their API.\n"
                "Try supplying --auth-token and --ct0 (see README)."
            )
        raise last_error

    def _parse_metadata(self, data: Dict[str, Any], space_id: str) -> SpaceMetadata:
        try:
            audio_space = data["data"]["audioSpace"]
        except KeyError:
            raise SpaceNotFoundError(f"Space {space_id!r} not found in response")

        meta = audio_space.get("metadata", {})
        state = meta.get("state", "Unknown")

        def _ts(ms: Optional[int]) -> Optional[datetime]:
            return datetime.fromtimestamp(ms / 1000, tz=timezone.utc) if ms else None

        creator = meta.get("creator_results", {}).get("result", {})
        legacy = creator.get("legacy", {})
        host_username = legacy.get("screen_name", "unknown")
        host_display_name = legacy.get("name", host_username)
        title = meta.get("title") or f"Space by @{host_username}"
        media_key = meta.get("media_key", "")

        if not media_key:
            raise APIError(f"No media_key in metadata for Space {space_id!r}")

        return SpaceMetadata(
            space_id=space_id,
            title=title,
            host_username=host_username,
            host_display_name=host_display_name,
            state=state,
            media_key=media_key,
            original_url=f"https://x.com/i/spaces/{space_id}",
            created_at=_ts(meta.get("created_at")),
            started_at=_ts(meta.get("started_at")),
            ended_at=_ts(meta.get("ended_at")),
            participant_count=meta.get("total_replay_watched", 0),
        )

    async def get_stream_url(self, media_key: str) -> str:
        """Return the master HLS playlist URL for *media_key*."""
        assert self._session is not None
        use_auth = bool(self._auth_token)

        if not use_auth:
            await self._ensure_guest_token()

        url = f"https://twitter.com/i/api/1.1/live_video_stream/status/{media_key}"

        if use_auth:
            headers = self._auth_headers()
            cookies = self._auth_cookies()
        else:
            headers = {**self._base_headers(), "x-guest-token": self._guest_token or ""}
            cookies = {}

        resp = await self._session.get(url, headers=headers, cookies=cookies)

        if resp.status == 404:
            raise ReplayUnavailableError(
                "The stream is not available. The host may not have enabled replays, "
                "or the Space has expired."
            )
        if resp.status != 200:
            raise APIError(f"Failed to get stream URL (HTTP {resp.status})")

        data = await resp.json()
        source = data.get("source", {})
        stream_url = source.get("location") or source.get("noRedirectPlaybackUrl")

        if not stream_url:
            raise APIError("No HLS stream URL found in live_video_stream response")

        logger.debug("Stream URL: %s…", stream_url[:80])
        return stream_url
