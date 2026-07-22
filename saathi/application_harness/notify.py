"""M17.11 harness-alert notification delivery — narrow transport contract, a local
durable transport, deterministic policy, and a concurrency-safe dispatcher.

This is NOT a platform-wide messaging rewrite: it is a small, harness-scoped layer
that turns M17.10 `run_alert` rows into durable, deduplicated, retryable
`run_alert_delivery` records (in the SAME ledger DB) and dispatches them through a
configured transport. External providers are optional and fail closed when not
configured; the local file transport works with no credentials.

Determinism: no LLM, no randomness, no real sleeps. Retry timing comes from the
ledger's fixed `RETRY_SCHEDULE`; the clock is injectable everywhere. Payloads are
owner-safe — they carry alert identity/class/severity only, never argv, output,
secrets, tokens, or provider responses.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from saathi.application_harness import run_ledger as L

# durable local transport output lives under the (gitignored) ledger data dir
_NOTIFY_DIR = L.ROOT / "data" / "application_harness_runs" / "notifications"

# error-summary bound (never store provider dumps / stack traces in full)
_ERR_MAX = 200


# ── owner-safe payload + result ─────────────────────────────────────────────
@dataclass(frozen=True)
class AlertNotification:
    alert_id: int
    run_id: str
    owner: str
    alert_class: str
    severity: str
    fingerprint: str
    message: str            # owner-safe, no argv/output/secrets

    def to_public(self) -> dict:
        return {"alert_id": self.alert_id, "run_id": self.run_id,
                "owner": self.owner, "alert_class": self.alert_class,
                "severity": self.severity, "fingerprint": self.fingerprint,
                "message": self.message}


@dataclass(frozen=True)
class DeliveryResult:
    ok: bool
    error_code: str = ""
    detail: str = ""
    idempotent: bool = False


def fingerprint(alert: dict) -> str:
    """Deterministic payload version — changes only if the alert's class/severity
    changes (a new episode is a new alert row / new id)."""
    basis = f"{alert.get('run_id')}|{alert.get('alert_class')}|{alert.get('severity')}"
    return hashlib.sha256(basis.encode()).hexdigest()[:24]


def build_notification(alert: dict) -> AlertNotification:
    return AlertNotification(
        alert_id=alert["id"], run_id=alert["run_id"], owner=alert.get("owner", ""),
        alert_class=alert["alert_class"], severity=alert["severity"],
        fingerprint=fingerprint(alert),
        message=f"harness run {alert['run_id']} is {alert['alert_class']} "
                f"(severity {alert['severity']})")


# ── transport contract ──────────────────────────────────────────────────────
class AlertTransport(Protocol):
    name: str

    def send(self, notification: AlertNotification) -> DeliveryResult:
        ...


class LocalFileTransport:
    """Durable, credential-free, idempotent local transport. Appends one owner-safe
    JSONL line per delivered notification under the ledger data dir; a repeat send
    of the same (alert, fingerprint) is a no-op that reports idempotent success.
    Never reports success unless the line is written + fsynced."""
    name = "local"

    def __init__(self, root: os.PathLike | str | None = None):
        self.root = Path(root) if root else _NOTIFY_DIR
        self.path = self.root / "local.jsonl"

    def _already(self, key: str) -> bool:
        if not self.path.exists():
            return False
        for line in self.path.read_text().splitlines():
            try:
                if json.loads(line).get("idem") == key:
                    return True
            except Exception:
                continue
        return False

    def send(self, notification: AlertNotification) -> DeliveryResult:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            key = f"{notification.alert_id}:{notification.fingerprint}"
            if self._already(key):
                return DeliveryResult(ok=True, idempotent=True)
            rec = {"idem": key, **notification.to_public()}
            with open(self.path, "a") as f:
                f.write(json.dumps(rec, separators=(",", ":")) + "\n")
                f.flush()
                os.fsync(f.fileno())
            return DeliveryResult(ok=True)
        except Exception as e:               # never claim success on a write failure
            return DeliveryResult(ok=False, error_code="local_write_failed",
                                  detail=str(e)[:_ERR_MAX])


class DisabledTransport:
    """A configured-but-disabled channel. Fails closed — never fakes success."""
    def __init__(self, name: str):
        self.name = name

    def send(self, notification: AlertNotification) -> DeliveryResult:
        return DeliveryResult(ok=False, error_code="transport_disabled",
                              detail=f"channel {self.name} disabled")


class UnconfiguredTransport:
    """An external channel requested without configuration. Fails closed with safe
    configuration evidence — no credential is fabricated, no live call is made."""
    def __init__(self, name: str):
        self.name = name

    def send(self, notification: AlertNotification) -> DeliveryResult:
        return DeliveryResult(ok=False, error_code="transport_unconfigured",
                              detail=f"channel {self.name} not configured")


# ── channel configuration (admin/operator controlled; secrets never here) ───
def default_config() -> dict:
    """Local channel enabled (no creds needed). External channels are declared
    unconfigured and fail closed until real secret-managed config exists."""
    return {"local": {"enabled": True}}


def build_transports(config: dict | None = None, *, root=None) -> dict[str, AlertTransport]:
    config = config if config is not None else default_config()
    transports: dict[str, AlertTransport] = {}
    for channel, cfg in config.items():
        if channel == "local":
            transports[channel] = (LocalFileTransport(root) if cfg.get("enabled")
                                   else DisabledTransport("local"))
        else:
            # external providers are deferred: fail closed unless a real,
            # secret-managed transport is wired in (none in this milestone).
            transports[channel] = UnconfiguredTransport(channel)
    return transports


def enabled_channels(config: dict | None = None) -> list[str]:
    config = config if config is not None else default_config()
    return [ch for ch, cfg in config.items() if cfg.get("enabled")]


# ── dispatcher ──────────────────────────────────────────────────────────────
class NotificationDispatcher:
    """Enqueues deliveries from OPEN alerts (deterministic policy) and dispatches
    dispatchable deliveries through the configured transports with lease-based
    concurrency safety. Injectable clock; no real sleeps."""

    def __init__(self, ledger: L.RunLedger | None = None, *, config: dict | None = None,
                 transports: dict | None = None, root=None):
        self.ledger = ledger or L.default_ledger()
        self.config = config if config is not None else default_config()
        self.transports = transports if transports is not None else \
            build_transports(self.config, root=root)

    # policy: which OPEN alerts should have deliveries, on which channels
    def enqueue(self, *, now=None) -> dict:
        created = []
        channels = enabled_channels(self.config)
        for alert in self.ledger.open_alerts():
            if alert.get("status") != "open":        # acknowledged → no new delivery
                continue
            if alert.get("alert_class") not in L.ALERTABLE:   # fail closed
                continue
            fp = fingerprint(alert)
            for ch in channels:
                r = self.ledger.create_delivery(
                    alert["id"], channel=ch, payload_fingerprint=fp,
                    owner=alert.get("owner", ""), destination_key=ch, now=now)
                if r.get("created"):
                    created.append(r["delivery_id"])
        return {"created": created}

    def dispatch_once(self, *, now=None, worker="dispatcher", limit=100,
                      lease_sec=120.0) -> dict:
        now = now if now is not None else L._now()
        # recover crash-after-claim leases first (restart safety)
        self.ledger.reclaim_stale_deliveries(now=now, lease_sec=lease_sec)
        delivered, failed, skipped = [], [], []
        for d in self.ledger.pending_dispatchable(now=now, limit=limit):
            did = d["id"]
            if not self.ledger.claim_delivery(did, worker=worker, now=now,
                                              lease_sec=lease_sec):
                skipped.append(did); continue
            self.ledger._event("harness.notification.attempted",
                               {"delivery_id": did, "channel": d["channel"]})
            alert = self.ledger.alert_by_id(d["alert_id"])
            if alert is None:                        # alert vanished → fail closed
                self.ledger.mark_attempt_failed(did, error_code="alert_missing", now=now)
                failed.append(did); continue
            transport = self.transports.get(d["channel"])
            if transport is None:
                self.ledger.mark_attempt_failed(did, error_code="no_transport", now=now)
                failed.append(did); continue
            try:
                res = transport.send(build_notification(alert))
            except Exception as e:                   # never trust a transport to be safe
                res = DeliveryResult(ok=False, error_code="transport_exception",
                                     detail=str(e)[:_ERR_MAX])
            if res.ok:
                self.ledger.mark_delivered(did, now=now)
                delivered.append(did)
            else:
                self.ledger.mark_attempt_failed(did, error_code=res.error_code,
                                                error_summary=res.detail, now=now)
                failed.append(did)
        return {"delivered": delivered, "failed": failed, "skipped": skipped,
                "dispatched_at": now}

    def run_once(self, *, now=None, worker="dispatcher") -> dict:
        eq = self.enqueue(now=now)
        dp = self.dispatch_once(now=now, worker=worker)
        return {"enqueued": eq["created"], **dp}


def default_dispatcher() -> NotificationDispatcher:
    return NotificationDispatcher()
