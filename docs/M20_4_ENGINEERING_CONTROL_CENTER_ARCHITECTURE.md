# M20.4 — Engineering Control Center Architecture

## Flow

```text
Operator / Control Center (read-only)
  → engineering_control_center_status()
  → EngineeringStore + settings + readiness + selection
  → versioned read model (no secrets)

Operator launch (opt-in flags)
  → approve-readonly (bound approval)  [required for claude_code]
  → launch --mode readonly
  → integrity baseline
  → Model adapter (mock / claude dry_run if binary missing)
  → poll + integrity checks
  → quarantine if mutation
  → validation + handoff
```

## Systems reused (not replaced)

Mission Engine, ExecutionGateway, Approval patterns (local bound approvals), Knowledge (optional context string only), Codebase Memory (untouched), Event Bus (optional), Run Ledger (untouched), Scheduler (untouched), Repair Loops (untouched), SafetyHarness (untouched), Trading Guardian (isolation only), Control Center aggregator cells, Engineering M20.0 store/orchestrator.

## JSON store note

File-backed JSON remains owner for engineering sessions. M20.4 adds `fcntl` locking, backups, lease reclaim. Future migration to a canonical ledger is optional technical debt—not required for pilot.
