# SaathiOS Technical Debt / Known Gaps

## Environment-blocked (need user action — NOT debt)
- macOS Accessibility grant → native Finder/TextEdit actuation.
- Cloud connector credentials (Gmail/Calendar/Telegram) → live connector ops.
- Safe staging account → authenticated browser workflow.
- GUI app installs (LibreOffice/Blender/Kdenlive) → more harness apps.

## Real debt (actionable without approval)
- Long-running harness task control: cancel + orphan-free timeout kill +
  live-enforced resource limits + durable run journal with crash reconciliation
  BUILT & live-proven (M17.8, task_control.py + run_journal.py). Remaining:
  pause/resume/checkpoint (deferred, larger).
- Production monitoring/alerting/incident-response automation absent.
- Harness registry persistence (data/application_harnesses/registry.json) written
  but not loaded on boot (in-memory bootstrap only).
- Multi-user isolation only probe-tested, not exercised with concurrent users.
- legacy saathi/connectors (pre-M15) telegram adapter = transitional exception,
  not yet wrapped under the platform adapter.

## Deferred (large / premature)
- Workflow Intelligence engine (gated: needs more live-execution proof first).
- Cloud/multi-tenant deployment, worker fleet, billing.
