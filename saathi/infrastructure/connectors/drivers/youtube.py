"""YouTube connector — AI Studio integration.

Read capabilities (search, get_video, channel stats) via the Data API v3 with an
API key. `upload_video`/`publish_video` are declared but require OAuth, so they
raise AuthRequired until an OAuth token is wired — the manifest still advertises
the capability so the registry can route to it once credentials exist.
"""
from __future__ import annotations

import os

from ..base import Connector, Health, Status, ConnectorError, AuthRequired
from ..manifest import Manifest

_READ = frozenset({"search", "get_video", "channel_stats"})
_WRITE = frozenset({"upload_video", "publish_video"})
_CAPS = _READ | _WRITE


class YouTubeConnector(Connector):
    id = "youtube"

    def __init__(self, api_key: str | None = None, oauth_token: str | None = None, transport=None):
        self._key = api_key if api_key is not None else os.getenv("YT_API_KEY", "")
        self._oauth = oauth_token if oauth_token is not None else os.getenv("YT_OAUTH_TOKEN", "")
        self._transport = transport

    def manifest(self) -> Manifest:
        return Manifest(
            id=self.id, display_name="YouTube", category="media", version=1,
            capabilities=_CAPS, permissions=frozenset({"outbound"}),
            requires_auth=True, cost=0.0, latency="medium", reliability=0.96,
            rate_limits={"units_per_day": 10000},
            health_checks=frozenset({"api_key", "quota"}))

    def authenticate(self) -> bool:
        return bool(self._key) and not self._key.startswith("YOUR")

    def _client(self, timeout=20):
        import httpx
        return httpx.Client(timeout=timeout, transport=self._transport,
                            base_url="https://www.googleapis.com/youtube/v3")

    def health(self) -> Health:
        if not self.authenticate():
            return Health(Status.AUTH_REQUIRED, "YT_API_KEY missing")
        try:
            with self._client(timeout=8) as c:
                r = c.get("/search", params={"part": "snippet", "q": "test",
                                             "maxResults": 1, "key": self._key})
            if r.status_code == 403:
                return Health(Status.DEGRADED, "quota exceeded or key restricted")
            r.raise_for_status()
            return Health(Status.OK, "Data API reachable")
        except Exception as e:
            return Health(Status.DOWN, str(e))

    def execute(self, capability: str, **payload):
        self._require(capability)
        if capability in _WRITE and not self._oauth:
            raise AuthRequired("youtube upload requires OAuth (set YT_OAUTH_TOKEN)")
        with self._client() as c:
            if capability == "search":
                r = c.get("/search", params={"part": "snippet", "q": payload["query"],
                          "maxResults": payload.get("limit", 5), "type": "video", "key": self._key})
            elif capability == "get_video":
                r = c.get("/videos", params={"part": "snippet,statistics",
                          "id": payload["video_id"], "key": self._key})
            elif capability == "channel_stats":
                r = c.get("/channels", params={"part": "statistics",
                          "id": payload["channel_id"], "key": self._key})
            else:
                raise ConnectorError(f"{capability} not implemented (OAuth upload path)")
        r.raise_for_status()
        return r.json()
