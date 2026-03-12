"""Twitter/X API client for fetching Space metadata and stream URLs.

Design notes
------------
Twitter does not offer a public API for Spaces. We use the same private GraphQL
and REST endpoints the web client uses, authenticated either with a *guest token*
(works for public, ended Spaces) or the user's own ``auth_token`` + ``ct0``
browser cookies (required for some restricted replays).

The GraphQL query ID for ``AudioSpaceById`` changes whenever Twitter redeploys.
We handle this in three tiers:
  1. Try a list of known IDs (fast, works until the next deploy).
  2. Auto-discover the current ID from Twitter's live JS bundle (always fresh).
  3. Scrape the Space page's __NEXT_DATA__ JSON as a final fallback.
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
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
TWITTER_BEARER = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

# Known AudioSpaceById query IDs (newest first). Used as a fast-path cache.
# When all return 404, we fall back to auto-discovery.
_KNOWN_QUERY_IDS = [
    "HPEisOmj1epUNLCWTYhUWw",  # current as of 2026-03
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

# Regex to extract AudioSpaceById query ID from Twitter's JS bundle.
# Handles both JSON-style ("queryId":"XXXX") and minified JS (queryId:"XXXX").
_QID_RE = re.compile(
    r'(?:"queryId"|queryId)\s*:\s*"([A-Za-z0-9_-]{15,30})"\s*,\s*'
    r'(?:"operationName"|operationName)\s*:\s*"AudioSpaceById"'
)

# Regex to find JS bundle URLs on the Twitter homepage.
_BUNDLE_RE = re.compile(
    r'https://abs\.twimg\.com/responsive-web/client-web/(?:shared~)?[a-zA-Z0-9._~-]+\.js'
)


class TwitterAPIClient:
    """Async context-manager client for Twitter/X private API calls."""

    def __init__(
        self,
        auth_token: Optional[str] = None,
        ct0: Optional[str] = None,
    ) -> None:
        self._auth_token = auth_token
        self._ct0 = ct0
        self._guest_token: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._discovered_query_id: Optional[str] = None

    async def __aenter__(self) -> "TwitterAPIClient":
        self._session = aiohttp.ClientSession(
            headers={"User-Agent": _USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=30, connect=10),
            max_line_size=65536,
            max_field_size=65536,
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._session:
            await self._session.close()

    # ── Headers / cookies ─────────────────────────────────────────────────────

    def _base_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {TWITTER_BEARER}",
            "Content-Type": "application/json",
            "x-twitter-client-language": "en",
            "x-twitter-active-user": "yes",
        }

    def _auth_headers(self) -> Dict[str, str]:
        h = self._base_headers()
        if self._ct0:
            h["x-csrf-token"] = self._ct0
        return h

    def _auth_cookies(self) -> Dict[str, str]:
        c: Dict[str, str] = {}
        if self._auth_token:
            c["auth_token"] = self._auth_token
        if self._ct0:
            c["ct0"] = self._ct0
        return c

    # ── Guest token ───────────────────────────────────────────────────────────

    async def _ensure_guest_token(self) -> None:
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

    # ── Dynamic query ID discovery ────────────────────────────────────────────

    async def _discover_query_id(self) -> Optional[str]:
        """Find the current AudioSpaceById query ID from Twitter's live JS bundle.

        Strategy:
          1. Fetch the Twitter homepage.
          2. Parse the inline webpack runtime script (c.u=) to get the chunk hash
             map, then fetch Space-related lazy chunks and scan for the query ID.
          3. Fall back to scanning external <script src=""> bundles.
        """
        assert self._session is not None

        if self._discovered_query_id:
            return self._discovered_query_id

        logger.debug("Attempting to discover AudioSpaceById query ID from Twitter JS…")

        try:
            resp = await self._session.get(
                "https://x.com/",
                headers={"Accept": "text/html"},
                allow_redirects=True,
            )
            if resp.status != 200:
                logger.debug("Homepage returned HTTP %s", resp.status)
                return None

            html = await resp.text()

            # ── Tier A: inline webpack chunk-map ─────────────────────────────
            qid = await self._discover_from_chunk_map(html)
            if qid:
                return qid

            # ── Tier B: external <script src=""> bundles ──────────────────────
            bundle_urls = list(dict.fromkeys(_BUNDLE_RE.findall(html)))
            logger.debug("Found %d external JS bundle URLs", len(bundle_urls))
            for bundle_url in bundle_urls[:10]:
                try:
                    bresp = await self._session.get(bundle_url)
                    if bresp.status != 200:
                        continue
                    js = await bresp.text()
                    match = _QID_RE.search(js)
                    if match:
                        qid = match.group(1)
                        logger.debug("Discovered query ID from external bundle: %s", qid)
                        self._discovered_query_id = qid
                        return qid
                except Exception as exc:
                    logger.debug("Bundle fetch error: %s", exc)
                    continue

        except Exception as exc:
            logger.debug("Query ID discovery failed: %s", exc)

        return None

    async def _discover_from_chunk_map(self, html: str) -> Optional[str]:
        """Parse the webpack runtime inline script to find the AudioSpaceDetail chunk.

        Twitter embeds a webpack runtime inline in the HTML.  It contains a function
        ``c.u = e => e + "." + {chunk_name: hash, ...}[e] + ".js"`` that maps each
        lazy-chunk name to its content hash.  We use that to build the correct CDN
        URL for the Space-related bundles, fetch them, and scan for the query ID.
        """
        assert self._session is not None

        cu_idx = html.find("c.u=")
        if cu_idx < 0:
            logger.debug("c.u= (webpack chunk map) not found in HTML")
            return None

        map_start = html.find("{", cu_idx)
        if map_start < 0:
            return None

        # Walk to the matching closing brace.
        depth, pos = 0, map_start
        while pos < len(html):
            if html[pos] == "{":
                depth += 1
            elif html[pos] == "}":
                depth -= 1
                if depth == 0:
                    break
            pos += 1

        chunk_map_raw = html[map_start : pos + 1]
        space_chunks = re.findall(
            r'"((?:bundle|shared|loader)[^"]*(?:[Ss]pace)[^"]*)":\s*"([a-f0-9]+)"',
            chunk_map_raw,
        )
        logger.debug("Found %d Space-related chunks in webpack chunk map", len(space_chunks))

        # Sort: AudioSpaceDetail first, then other AudioSpace chunks.
        priority = ["AudioSpaceDetail", "AudioSpaceDiscovery", "AudioSpacebarScreen"]

        def _rank(item: tuple) -> int:
            for i, kw in enumerate(priority):
                if kw in item[0]:
                    return i
            return len(priority)

        space_chunks.sort(key=_rank)

        base = "https://abs.twimg.com/responsive-web/client-web/"
        for chunk_name, chunk_hash in space_chunks[:10]:
            url = f"{base}{chunk_name}.{chunk_hash}.js"
            try:
                bresp = await self._session.get(url)
                if bresp.status != 200:
                    logger.debug(
                        "Chunk %s…: HTTP %s", chunk_name[:50], bresp.status
                    )
                    continue
                js = await bresp.text()
                match = _QID_RE.search(js)
                if match:
                    qid = match.group(1)
                    logger.debug(
                        "Discovered query ID from chunk %s: %s", chunk_name[:50], qid
                    )
                    self._discovered_query_id = qid
                    return qid
            except Exception as exc:
                logger.debug("Chunk fetch error (%s): %s", chunk_name[:50], exc)
                continue

        return None

    # ── Page-scrape fallback ──────────────────────────────────────────────────

    async def _scrape_space_page(self, space_id: str) -> Optional[SpaceMetadata]:
        """Scrape the Space page and extract metadata from __NEXT_DATA__.

        Twitter embeds the server-side render data in a JSON blob inside the page.
        This is a fragile but useful fallback when the GraphQL API is unavailable.
        """
        assert self._session is not None
        logger.debug("Attempting page scrape for Space %s…", space_id)

        url = f"https://x.com/i/spaces/{space_id}"
        headers = {
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }
        cookies = self._auth_cookies() if self._auth_token else {}

        try:
            resp = await self._session.get(url, headers=headers, cookies=cookies)
            if resp.status != 200:
                logger.debug("Space page returned HTTP %s", resp.status)
                return None

            html = await resp.text()
        except Exception as exc:
            logger.debug("Space page fetch error: %s", exc)
            return None

        # Look for __NEXT_DATA__ JSON blob.
        nd_match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
            html,
            re.DOTALL,
        )
        if not nd_match:
            logger.debug("__NEXT_DATA__ not found in Space page")
            return None

        try:
            nd = json.loads(nd_match.group(1))
        except json.JSONDecodeError as exc:
            logger.debug("__NEXT_DATA__ JSON parse error: %s", exc)
            return None

        # Walk the nested structure to find audioSpace data.
        try:
            # Path varies — try common locations.
            props = nd.get("props", {})
            page_props = props.get("pageProps", {})

            # Try multiple known paths
            audio_space = (
                page_props.get("audioSpace")
                or page_props.get("data", {}).get("audioSpace")
                or {}
            )
            meta = audio_space.get("metadata", {})

            if not meta:
                logger.debug("No audioSpace metadata found in __NEXT_DATA__")
                return None

            media_key = meta.get("media_key", "")
            if not media_key:
                logger.debug("No media_key in __NEXT_DATA__ metadata")
                return None

            def _ts(ms: Optional[Any]) -> Optional[datetime]:
                if not ms:
                    return None
                try:
                    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
                except (TypeError, ValueError):
                    return None

            creator = meta.get("creator_results", {}).get("result", {})
            legacy = creator.get("legacy", {})
            host_username = legacy.get("screen_name", "unknown")
            host_display_name = legacy.get("name", host_username)
            title = meta.get("title") or f"Space by @{host_username}"

            return SpaceMetadata(
                space_id=space_id,
                title=title,
                host_username=host_username,
                host_display_name=host_display_name,
                state=meta.get("state", "Unknown"),
                media_key=media_key,
                original_url=f"https://x.com/i/spaces/{space_id}",
                created_at=_ts(meta.get("created_at")),
                started_at=_ts(meta.get("started_at")),
                ended_at=_ts(meta.get("ended_at")),
                participant_count=meta.get("total_replay_watched", 0),
            )

        except Exception as exc:
            logger.debug("__NEXT_DATA__ parsing error: %s", exc)
            return None

    # ── GraphQL call (single query ID) ────────────────────────────────────────

    async def _try_graphql(
        self,
        qid: str,
        space_id: str,
        use_auth: bool,
    ) -> Optional[SpaceMetadata]:
        """Try fetching Space metadata with one query ID.

        Returns SpaceMetadata on success, None if the query ID is rejected (404/400),
        raises on auth errors or access-control errors.
        """
        assert self._session is not None

        variables = json.dumps({**_GRAPHQL_VARS, "id": space_id})
        features = json.dumps(_FEATURES)
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
            logger.debug("Network error for query ID %s: %s", qid, exc)
            return None

        logger.debug("Query ID %s → HTTP %s", qid, resp.status)

        if resp.status in (400, 404):
            # Outdated or unknown query ID — try the next one.
            return None

        if resp.status == 401:
            raise AuthenticationError(
                "Twitter returned 401 Unauthorized.\n"
                "Supply your auth token:\n"
                "  --auth-token YOUR_AUTH_TOKEN  (or TWITTER_AUTH_TOKEN env var)\n"
                "  --ct0 YOUR_CT0_TOKEN          (or TWITTER_CT0 env var)\n"
                "See README for instructions."
            )

        if resp.status == 403:
            raise AuthenticationError(
                "Twitter returned 403 Forbidden — this Space requires a logged-in account.\n"
                "Supply --auth-token and --ct0 (see README)."
            )

        if resp.status != 200:
            logger.debug("Unexpected HTTP %s for query ID %s", resp.status, qid)
            return None

        data = await resp.json()

        if "errors" in data and data["errors"]:
            msgs = "; ".join(e.get("message", "unknown") for e in data["errors"])
            if any(
                kw in msgs.lower()
                for kw in ("authorization", "forbidden", "permission", "not authorized")
            ):
                raise AuthenticationError(
                    f"Access denied: {msgs}\n"
                    "This Space may require a logged-in account.\n"
                    "Supply --auth-token and --ct0 (see README)."
                )
            logger.debug("GraphQL errors for query ID %s: %s", qid, msgs)
            return None

        try:
            return self._parse_metadata(data, space_id)
        except (KeyError, TypeError, ValueError) as exc:
            logger.debug("Parse error for query ID %s: %s", qid, exc)
            return None

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_space_metadata(self, space_id: str) -> SpaceMetadata:
        """Fetch metadata for *space_id* using a three-tier strategy:

        1. Known hardcoded query IDs (fast).
        2. Auto-discovered query ID from Twitter's live JS bundle.
        3. Page-scrape __NEXT_DATA__ fallback.
        """
        use_auth = bool(self._auth_token)
        if not use_auth:
            await self._ensure_guest_token()

        # ── Tier 1: known query IDs ───────────────────────────────────────────
        for qid in _KNOWN_QUERY_IDS:
            result = await self._try_graphql(qid, space_id, use_auth)
            if result:
                return result

        # ── Tier 2: auto-discover query ID from live JS ───────────────────────
        discovered = await self._discover_query_id()
        if discovered and discovered not in _KNOWN_QUERY_IDS:
            logger.debug("Trying discovered query ID: %s", discovered)
            result = await self._try_graphql(discovered, space_id, use_auth)
            if result:
                return result

        # ── Tier 3: page-scrape __NEXT_DATA__ ────────────────────────────────
        result = await self._scrape_space_page(space_id)
        if result:
            logger.debug("Got metadata via page scrape")
            return result

        raise SpaceNotFoundError(
            f"Could not retrieve metadata for Space {space_id!r}.\n"
            "Possible reasons:\n"
            "  • The Space no longer exists or the URL is wrong\n"
            "  • The Space requires a logged-in account (try --auth-token / --ct0)\n"
            "  • Twitter has changed their API (open an issue on GitHub)"
        )

    def _parse_metadata(self, data: Dict[str, Any], space_id: str) -> SpaceMetadata:
        try:
            audio_space = data["data"]["audioSpace"]
        except KeyError:
            raise SpaceNotFoundError(f"Space {space_id!r} not found in response")

        meta = audio_space.get("metadata", {})

        def _ts(ms: Optional[Any]) -> Optional[datetime]:
            if not ms:
                return None
            try:
                return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
            except (TypeError, ValueError):
                return None

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
            state=meta.get("state", "Unknown"),
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

        data = await resp.json(content_type=None)
        source = data.get("source", {})
        stream_url = source.get("location") or source.get("noRedirectPlaybackUrl")

        if not stream_url:
            raise APIError("No HLS stream URL found in live_video_stream response")

        logger.debug("Stream URL: %s…", stream_url[:80])
        return stream_url
