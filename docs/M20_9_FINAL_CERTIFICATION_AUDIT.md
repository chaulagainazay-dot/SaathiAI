# M20.9 — Final Certification Audit

**Starting HEAD:** `947d267` (M20.7)  
**M20.8:** INTENTIONALLY_SKIPPED (see `docs/M20_8_STATUS.md`)  
**M20.6 live:** BLOCKED (environment)  

---

## C2.1 Engineering architecture inventory

| Component | Path | Authority | Default | Persistence | Disposition |
|-----------|------|-----------|---------|-------------|-------------|
| Engineering Orchestrator | `saathi/engineering/orchestrator.py` | Lifecycle supervision | disabled | store + ledger events | CANONICAL |
| EngineeringStore | `saathi/engineering/store.py` | Backlog/sessions/approvals | local data/ | JSON + lock | CANONICAL eng state |
| Session ledger | `saathi/engineering/session_ledger.py` | Append-only evidence | always | JSONL hash chain | CANONICAL eng evidence |
| Integrity | `saathi/engineering/integrity.py` | Repo snapshot/diff | n/a | ephemeral + evidence files | CANONICAL |
| Integrity evidence | `saathi/engineering/evidence.py` | Baseline/check/violation | n/a | `integrity_evidence/` | CANONICAL |
| Recovery | `saathi/engineering/recovery.py` | Stale/crash/resume plan | n/a | mutates sessions | CANONICAL |
| Approvals | `saathi/engineering/approval.py` | RO session binding | n/a | approvals.json | CANONICAL |
| Read model / CC facet | `read_model.py`, `control_center_facet.py` | Read-only | n/a | none | READ_ONLY_AGGREGATOR |
| Adapters | `adapters/` | Process launch | launch off | none | CANONICAL |
| CLI | `engineering/cli.py` | Operator | n/a | none | CANONICAL |
| Validation / stop / retry | respective modules | Policy | n/a | ledger/history | CANONICAL |

Production reachable: **no** (defaults off; pilot branch only).

---

## C2.2 Inference architecture inventory

| Component | Path | Direct engine? | Default | Disposition |
|-----------|------|----------------|---------|-------------|
| ModelRouter | `saathi/model_router.py` | no | n/a | CANONICAL selection |
| Governed path | `inference/gateway_path.py` | via adapter only | gateway off | CANONICAL local path |
| Ollama adapter | `inference/adapters/ollama.py` | yes (adapter) | off | CANONICAL_LOCAL |
| Compat / rollout | `compat.py`, `caller_rollout.py` | no | legacy | CANONICAL adoption |
| Callers | `cheap_llm.py`, `prose.py` | **no** | legacy | SELECTED (M20.3) |
| Certification | `certification.py`, `cert_corpus.py` | via governed | n/a | CANONICAL cert |
| Live validation | `live_validation.py` | adapter | n/a | CANONICAL helper |
| M20 console inference facet | `m20_console/status.py` | no | n/a | READ_ONLY_AGGREGATOR |

Cloud fallback default: **off**. Tool use: **false** on governed requests. Streaming: not required for pilot.

---

## C2.3 Duplicate-authority inventory

| Concern | Finding | Classification |
|---------|---------|----------------|
| Mission Engine | Unrelated harness missions | CANONICAL (separate domain) |
| Engineering orchestrator | Single package | CANONICAL |
| ModelRouter | Single | CANONICAL |
| ExecutionGateway | Single; inference via ModelGateway path | CANONICAL |
| Run ledger | Harness only; eng has session_ledger | CANONICAL + separate eng ledger |
| M20 console | Aggregate only | READ_ONLY_AGGREGATOR |
| Direct Ollama from callers | Absent in cheap_ask/prose | FAIL_CLOSED |
| Second OJ runtime | Not present | n/a |
| DUPLICATE_BLOCKING | **None unresolved** | — |

---

## C3 End-to-end flows (documented)

1. **Engineering RO session** — approval → ledger → integrity baseline → adapter (mock/claude dry_run) → monitor → validation → integrity check → handoff/CC  
2. **Opt-in inference** — rollout → compat → governed path → ModelRouter → engine → evidence (or legacy if mode legacy)  
3. **Blocked local model** — M20.6 BLOCKED → no download → no cloud escape → legacy default remains  
4. **M20 console** — eng + inf + flags → read-only JSON; no store mutation  

---

## Flag catalog

Authoritative machine-checkable catalog: `saathi/m20_console/flags.py` (`FLAG_CATALOG`, `flag_snapshot()`, `disable_procedure()`).

Invariants enforced by design/tests:

* Eng orch/launch/writes/commits/pushes default off  
* Inference + gateway default off  
* Rollout default legacy  
* Console read-only  
* TG not controlled by M20 flags  

---

## M20.6 honesty

Live local model certification remains **BLOCKED** unless new evidence appears. M20.9 does not reclassify as certified.

---

## Readiness (preview — finalized in M20.10)

| Capability | Level |
|------------|-------|
| Engineering orchestrator pilot | deterministic-tested, default-off |
| RO agent sessions | deterministic-tested, mock pilot |
| Session ledger / recovery | deterministic-tested |
| Governed inference path | deterministic-tested, default-off |
| Opt-in callers (2) | deterministic-tested, legacy default |
| Live small model | **environment-blocked** |
| M20 console | deterministic-tested, read-only |
| Production deployment | **not ready** |
