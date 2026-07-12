"""M17.10 harness run monitor — deterministic stuck-run detection + alerting.

A read-mostly sweep over the M17.9 run ledger. It does NOT introduce a second
monitoring stack: it reuses the ledger's `classify()` + `reconcile_stale` path and
the ledger's own deduplicated alert store, and its alerts flow into the existing
Control Center attention surface + event bus.

Per sweep, for each ACTIVE run:
- `heartbeat_stale`  → raise a deduplicated `medium` alert (still maybe alive, quiet);
- `cancellation_stuck` → raise a deduplicated `high` alert (cancel not honoured);
- `process_missing`  → reconcile via the ledger (idempotent, live-safe crash
  recovery — the ONLY run mutation); the terminal transition auto-resolves alerts;
- `active`           → self-heal: resolve any stale/cancel alerts (run recovered).

Deterministic: `now`, thresholds, and `is_alive` are injectable; no randomness. A
stuck run alerts ONCE per episode (ledger dedup), so the sweep is safe to run on a
tight schedule without alert storms. The sweep never reruns work and never touches
a live process.
"""
from __future__ import annotations

from saathi.application_harness.run_ledger import (RunLedger, default_ledger,
                                                   ALERTABLE, ALERT_SEVERITY, _now,
                                                   _pid_alive)

_SELF_HEAL_CLASSES = ("heartbeat_stale", "cancellation_stuck")


class HarnessRunMonitor:
    """One monitor over one ledger. Stateless beyond the ledger it wraps."""

    def __init__(self, ledger: RunLedger | None = None):
        self.ledger = ledger or default_ledger()

    def sweep(self, *, now=None, stale_sec: float = 30.0,
              cancel_stuck_sec: float = 60.0, is_alive=None) -> dict:
        now = now if now is not None else _now()
        alive = is_alive or _pid_alive
        raised, recovered = [], []
        class_counts: dict[str, int] = {}
        for run in self.ledger.list_active():
            klass = self.ledger.classify(run, now=now, stale_sec=stale_sec,
                                         cancel_stuck_sec=cancel_stuck_sec,
                                         is_alive=alive)
            class_counts[klass] = class_counts.get(klass, 0) + 1
            rid = run["run_id"]
            if klass == "process_missing":
                r = self.ledger.reconcile_run(rid, is_alive=alive)
                if r.get("reconciled"):
                    recovered.append(rid)
            elif klass in ALERTABLE:
                out = self.ledger.raise_alert(rid, alert_class=klass,
                                              severity=ALERT_SEVERITY[klass],
                                              owner=run.get("owner", ""),
                                              detail=f"state={run['state']}")
                if out.get("raised"):
                    raised.append({"run_id": rid, "alert_class": klass})
            else:                              # active/terminal → self-heal
                for cls in _SELF_HEAL_CLASSES:
                    self.ledger.resolve_alerts(rid, alert_class=cls)
        return {"swept_at": now, "active_swept": sum(class_counts.values()),
                "class_counts": class_counts, "alerts_raised": raised,
                "recovered": recovered,
                "open_alerts": len(self.ledger.open_alerts())}

    def open_alerts(self, owner: str | None = None) -> list[dict]:
        return self.ledger.open_alerts(owner)

    def attention_items(self, owner: str | None = None) -> list[dict]:
        """Owner-safe, severity-tagged items for the Control Center attention
        surface. No argv / output / secrets."""
        items = []
        for a in self.ledger.open_alerts(owner):
            items.append({"severity": a["severity"], "kind": "harness_run",
                          "message": f"run {a['run_id']} {a['alert_class']}"
                                     + (f" ({a['status']})" if a["status"] != "open" else ""),
                          "link": "/control/harnesses"})
        return items


def default_monitor() -> HarnessRunMonitor:
    return HarnessRunMonitor()
