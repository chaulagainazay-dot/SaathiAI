"""ConnectorRegistry — get/by_capability/best + health-aware execution.

    registry.get("telegram")
    registry.by_capability("send_video")          # all that can
    registry.best("video_generation")             # ranked: health→reliability→cost→latency
    registry.execute(capability="send_text", chat_id=..., text=...)

`best`/`execute` pick the strongest healthy connector, mirroring the Model
Router. Health transitions publish standardized events to the Event Fabric so
Executive Intelligence learns "YouTube token expired" without polling.
"""
from __future__ import annotations

from .base import (
    Connector, ConnectorEvent, ConnectorError, Status, AuthRequired, RateLimited,
)


class ConnectorRegistry:
    def __init__(self, bus=None):
        self._connectors: dict[str, Connector] = {}
        self._bus = bus                      # injectable Event Fabric (optional)
        self._last_status: dict[str, Status] = {}

    # ── registration ────────────────────────────────────────────────────
    def register(self, connector: Connector) -> Connector:
        self._connectors[connector.id] = connector
        return connector

    def get(self, connector_id: str) -> Connector:
        try:
            return self._connectors[connector_id]
        except KeyError:
            raise ConnectorError(f"no connector registered as {connector_id!r}")

    def all(self) -> list[Connector]:
        return list(self._connectors.values())

    # ── discovery ───────────────────────────────────────────────────────
    def by_capability(self, capability: str) -> list[Connector]:
        return [c for c in self._connectors.values() if c.supports(capability)]

    def ranked(self, capability: str) -> list[Connector]:
        """Healthy+authenticated connectors for a capability, best-first.
        Rank: usable-health, then reliability↓, cost↑, latency↑ — this is the
        API ★ > Browser > Human ordering when they advertise the same capability."""
        scored = []
        for c in self.by_capability(capability):
            m = c.manifest()
            if m.requires_auth and not c.authenticate():
                continue
            h = c.health()
            self._note_status(c.id, h.status, h.metrics)
            if not h.status.usable:
                continue
            scored.append((0 if h.status is Status.OK else 1,
                           -m.reliability, m.cost, m.latency_rank, c))
        scored.sort(key=lambda t: t[:4])
        return [t[4] for t in scored]

    def best(self, capability: str) -> Connector | None:
        chain = self.ranked(capability)
        return chain[0] if chain else None

    # ── execution ───────────────────────────────────────────────────────
    def execute(self, capability: str, *, connector_id: str | None = None, **payload):
        """Run a capability, falling through the ranked connectors on failure —
        so `publish_video` tries the API, then browser, then the human driver,
        and the department never learns which mode succeeded."""
        import time
        chain = [self.get(connector_id)] if connector_id else self.ranked(capability)
        if not chain:
            raise ConnectorError(f"no healthy connector serves {capability!r}")
        last_err: Exception | None = None
        for i, target in enumerate(chain):
            try:
                result = target.execute(capability, **payload)
                target._last_success = time.time()
                self._emit(ConnectorEvent.EXECUTED,
                           target.id, {"capability": capability, "mode": target.id})
                return result
            except (AuthRequired, RateLimited) as e:
                target._last_error = str(e); last_err = e
                ev = ConnectorEvent.AUTH_REQUIRED if isinstance(e, AuthRequired) else ConnectorEvent.RATE_LIMITED
                self._emit(ev, target.id, {"error": str(e)})
            except Exception as e:
                target._last_error = str(e); last_err = e
                self._emit(ConnectorEvent.FAILED, target.id,
                           {"capability": capability, "error": str(e)})
            if i + 1 < len(chain):
                self._emit(ConnectorEvent.DEGRADED, target.id,
                           {"capability": capability, "falling_back_to": chain[i + 1].id})
        raise last_err if last_err else ConnectorError(f"no connector served {capability!r}")

    # ── health / diagnostics ────────────────────────────────────────────
    def health_all(self) -> dict[str, dict]:
        out = {}
        for c in self._connectors.values():
            h = c.health()
            self._note_status(c.id, h.status, h.metrics)
            out[c.id] = {"status": h.status.value, "light": h.status.light, "detail": h.detail,
                         "metrics": h.metrics}
        return out

    def diagnostics(self) -> list[dict]:
        return [c.diagnostics() for c in self._connectors.values()]

    # ── event plumbing ──────────────────────────────────────────────────
    def _note_status(self, cid: str, status: Status, metrics: dict | None = None) -> None:
        prev = self._last_status.get(cid)
        self._last_status[cid] = status
        # quota warnings fire regardless of transition (a live threshold signal)
        q = (metrics or {}).get("quota_remaining")
        if q is not None and q <= 15:
            self._emit(ConnectorEvent.QUOTA_WARNING, cid, {"quota_remaining": q})
        if prev is not None and prev is status:
            return  # status-transition events only fire on change
        if status is Status.OK and prev is not None:
            self._emit(ConnectorEvent.CONNECTED, cid, {})
        elif status is Status.DEGRADED:
            self._emit(ConnectorEvent.DEGRADED, cid, {})
        elif status is Status.AUTH_REQUIRED:
            self._emit(ConnectorEvent.AUTH_REQUIRED, cid, {})
        elif status is Status.DOWN:
            self._emit(ConnectorEvent.DISCONNECTED, cid, {})
            self._emit(ConnectorEvent.FAILED, cid, {})

    def _emit(self, event: ConnectorEvent, connector_id: str, payload: dict) -> None:
        if self._bus is None:
            return
        try:
            self._bus.publish_sync(event.value, {"connector": connector_id, **payload})
        except Exception:
            pass  # telemetry must never break a real call


# Process-wide default registry (bus wired lazily by callers that want events).
registry = ConnectorRegistry()
