# SaathiOS Technical Debt / Known Gaps

## Environment-blocked (need user action — NOT debt)
- macOS Accessibility grant → native Finder/TextEdit actuation.
- Cloud connector credentials (Gmail/Calendar/Telegram) → live connector ops.
- Safe staging account → authenticated browser workflow.
- GUI app installs (LibreOffice/Blender/Kdenlive) → more harness apps.

## Real debt (actionable without approval)
- Long-running harness task control: cancel + orphan-free timeout kill +
  live-enforced resource limits BUILT & live-proven (M17.8). Durable run tracking
  upgraded from the single-process JSONL journal to a **transactional SQLite run
  ledger** (M17.9, run_ledger.py): CAS state machine, one-claimant-per-run,
  terminal immutability, ownership-safe cancel, exactly-once idempotent crash
  recovery, heartbeats + stuck-run classification, recovery ops, safe reversible
  JSONL migration, admin-maintenance CLI (OS-identity, audited — no caller-supplied
  identity trusted), Control Center read model, and a dedicated green blocking
  Critical Manifest entry. Multi-PROCESS concurrency proven (spawn, not threads).
  Remaining: pause/resume/checkpoint (contract_ready only — process suspension is
  NOT application checkpointing); multi-user LOAD (vs. cross-user gates); a
  production monitoring/alerting dashboard on top of the ledger read model.
- Production monitoring/alerting/incident-response automation absent (M17.9 ledger
  read model + reconcile_stale attention items are the substrate for it).
- Harness registry persistence (data/application_harnesses/registry.json) written
  but not loaded on boot (in-memory bootstrap only).
- Multi-user isolation only probe-tested, not exercised with concurrent users.
- legacy saathi/connectors (pre-M15) telegram adapter = transitional exception,
  not yet wrapped under the platform adapter.

## Deferred (large / premature)
- Workflow Intelligence engine (gated: needs more live-execution proof first).
- Cloud/multi-tenant deployment, worker fleet, billing.
