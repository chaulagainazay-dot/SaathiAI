"""GitHub connector — reference driver (stable, already important).

Wraps the REST API over httpx. Transport injectable for tests.
"""
from __future__ import annotations

import os

from ..base import Connector, Health, Status, ConnectorError, RateLimited, AuthRequired
from ..manifest import Manifest

_CAPS = frozenset({"get_user", "get_repo", "list_issues", "create_issue", "get_file"})


class GitHubConnector(Connector):
    id = "github"

    def __init__(self, token: str | None = None, transport=None):
        self._token = token if token is not None else os.getenv("GITHUB_TOKEN", "")
        self._transport = transport

    def manifest(self) -> Manifest:
        return Manifest(
            id=self.id, display_name="GitHub", category="developer", version=1,
            capabilities=_CAPS, permissions=frozenset({"outbound"}),
            requires_auth=True, cost=0.0, latency="low", reliability=0.98,
            rate_limits={"requests_per_hour": 5000}, health_checks=frozenset({"token", "api"}))

    def authenticate(self) -> bool:
        return bool(self._token) and not self._token.startswith("YOUR")

    def _client(self, timeout=20):
        import httpx
        headers = {"Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return httpx.Client(timeout=timeout, transport=self._transport,
                            base_url="https://api.github.com", headers=headers)

    def health(self) -> Health:
        if not self.authenticate():
            return Health(Status.AUTH_REQUIRED, "GITHUB_TOKEN missing")
        try:
            with self._client() as c:
                r = c.get("/rate_limit")
            if r.status_code == 401:
                return Health(Status.AUTH_REQUIRED, "token rejected")
            r.raise_for_status()
            core = r.json().get("resources", {}).get("core", {})
            remaining, limit = core.get("remaining", 1), core.get("limit", 1) or 1
            pct_remaining = round(100 * remaining / limit)
            metrics = {"quota_remaining": pct_remaining, "quota_pct": 100 - pct_remaining}
            if remaining == 0:
                return Health(Status.DEGRADED, "rate limit exhausted", metrics)
            status = Status.DEGRADED if pct_remaining <= 10 else Status.OK
            return Health(status, f"{remaining}/{limit} left", metrics)
        except Exception as e:
            return Health(Status.DOWN, str(e))

    def execute(self, capability: str, **payload):
        self._require(capability)
        with self._client() as c:
            if capability == "get_user":
                r = c.get("/user")
            elif capability == "get_repo":
                r = c.get(f"/repos/{payload['owner']}/{payload['repo']}")
            elif capability == "list_issues":
                r = c.get(f"/repos/{payload['owner']}/{payload['repo']}/issues",
                          params={"state": payload.get("state", "open")})
            elif capability == "create_issue":
                r = c.post(f"/repos/{payload['owner']}/{payload['repo']}/issues",
                           json={"title": payload["title"], "body": payload.get("body", "")})
            elif capability == "get_file":
                r = c.get(f"/repos/{payload['owner']}/{payload['repo']}/contents/{payload['path']}")
            else:  # unreachable — _require already gated
                raise ConnectorError(capability)
        if r.status_code == 401:
            raise AuthRequired("github 401")
        if r.status_code == 403 and "rate limit" in (r.text or "").lower():
            raise RateLimited("github rate limit")
        r.raise_for_status()
        return r.json()
