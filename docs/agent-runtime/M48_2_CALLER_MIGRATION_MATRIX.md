# M48.2 — Caller Migration Matrix

| Caller | Status |
|---|---|
| `api.create_run` | **MIGRATED** |
| `ChatEngine.start_orchestration` | **MIGRATED** |
| CLI `run` / `run-team` | **MIGRATED** |
| `Orchestrator.create_run` | **WRAPPED** (always validates unless `skip_contract`) |
| `ChatEngine.run_agent` | **KEPT_COMPATIBILITY** (M8 single turn) |
| IELTS agents | **DEFERRED** / OUT_OF_SCOPE |
| Finance trade execution | **PROHIBITED** |
