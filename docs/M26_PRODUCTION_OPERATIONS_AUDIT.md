# M26 Production Operations Audit

**Branch:** `milestone/m7-security-engine`  
**Starting HEAD:** `d543c9e`  
**Date:** 2026-07-17  
**Operator authorization:** M26 only (production inference operations)

---

## 1. Roadmap vs authorized scope

| Source | M26 definition |
|--------|----------------|
| `docs/M21_39_MASTER_PROGRAM_ROADMAP.md` | Browser, Files, Gmail, Calendar, GitHub, Research |
| Operator mission (this session) | Production inference operations, observability, controlled rollout |
| `docs/AUTONOMOUS_LOOP_STATE.json` | Next = M26 operator authorize only (post M25 cert) |

**Decision:** Follow **operator-authorized M26** (inference operations). The M21.39 connector scope is deferred; record as technical debt / future milestone. Do not implement Gmail/browser connectors in this milestone.

---

## 2. M25 certified baseline (preserve)

```text
production_certified = true (when package evidence fresh)
certification_blockers = []
full suite green
live local provider historically verified (dual evidence)
cloud fallback = disabled
residual exceptions = 0
Trading Guardian = UNCHANGED / UNENGAGED
```

Package evidence: `docs/evidence/m25/cert/`  
Architecture: `docs/M25_PRODUCTION_CERTIFICATION.md`

---

## 3. Existing capabilities to reuse

| Capability | Location | Reuse plan |
|------------|----------|------------|
| Runtime gate / production cert | `saathi/inference/runtime_gate.py` | Readiness consumes; never force certified |
| Package evidence | `saathi/inference/cert_evidence.py` | Fingerprint freshness; historical cert separate |
| Live dual evidence | `saathi/inference/live_cert_m25.py` | status view; no erase on RAM drop |
| Memory selection rule | `certification.memory_selection_ok` / `SELECTION_SAFETY_MARGIN_GB` | Resource guardian only |
| Hardware profile | `saathi/inference/hardware.py` | available_memory_gb, free_disk_gb |
| Circuit breaker | `saathi/inference/circuit_breaker.py` + durable store | Provider supervision |
| Reservations / recovery | `governance_store.recover_stale_reservations` | recover / crash reconcile |
| Config | `saathi/inference/config.py` | env-based settings pattern |
| Event bus | `saathi/events/bus.py` / `saathi.events` | operational events (redacted) |
| Control Center CLI | `saathi/m20_console` | add inference-ops status facet |
| Process status | `saathi/ops/process.py` | pattern only (no process kill) |
| Release check | `saathi/inference/release_check.py` | validation sequence |
| Atomic evidence writes | cert_evidence / live_cert patterns | ops state + incidents |

---

## 4. Operational entry points (current)

| Entry | Role |
|-------|------|
| `python -m saathi.inference.runtime_gate` | certification decision |
| `python -m saathi.inference.release_check` | static architecture |
| `python -m saathi.inference.live_cert_m25` | live cert / discover |
| `python -m saathi.inference.cert_evidence` | package evidence |
| `python -m saathi.m20_console runtime-readiness` | console snapshot |
| `python -m saathi.ops` | backup/db/release (not inference lifecycle) |

**Gap:** No start/status/readiness/health/drain/stop/restart/recover for inference ops.

---

## 5. Startup / shutdown today

* Inference is library/gateway path — no SaathiOS-owned inference daemon.
* Ollama is **external** process; SaathiOS must not claim ownership.
* No drain, grace period, or ops ownership lease for inference.

---

## 6. Provider process ownership

```text
external provider process  = Ollama (operator-managed)
SaathiOS provider session  = governed adapter call path
SaathiOS inference ops     = M26 lifecycle + readiness (this milestone)
```

---

## 7. Health / readiness signals (current)

* `hardware.HardwareProfile` — mem/disk
* `runtime_gate` / `detect_live_provider_status` — cert + live
* `circuit_breaker` — OPEN blocks provider
* `prod_config` / settings — posture
* No typed READY / DEGRADED / DRAINING ops statuses

---

## 8. Memory pressure

* M25 formula: `available >= 0.8 + model_budget` (1.5B → 1.8 GB)
* Temporary RAM must not erase historical cert (already dual-evidence)

---

## 9. Circuit breakers / monitoring / alerts

* Durable provider circuits (M24) — reuse
* Event bus exists — emit redacted ops events
* Storage/Telegram alerts exist for disk — do not auto-kill processes
* Engineering monitor — do not invent second monitor; emit events only

---

## 10. Missing controls (M26 scope)

1. Canonical inference ops lifecycle  
2. Health vs readiness distinction  
3. Resource guardian (mem/disk/concurrency/cooldown)  
4. Provider ops state machine (session-level, not Ollama PID ownership)  
5. Rollout modes OFF/SHADOW/CANARY/ACTIVE/DRAINING  
6. Rollback to OFF + drain  
7. Typed incident records with dedupe  
8. Operator status view  

---

## 11. Environment-blocked items

* Live smoke may be MEMORY_BLOCKED on 8 GB host  
* Model unload optional and **disabled by default**  
* No model download/pull in M26  
* Ollama start/stop not claimed by SaathiOS  

---

## 12. Explicit non-goals

* M27 / Trading Guardian activation  
* M21.39 connector M26 (Gmail/browser)  
* New event bus, circuit breaker, evidence store, or daemon framework  
* Cloud fallback, paid APIs, public deploy  
* Automatic model delete / disk wipe / kill unrelated apps  
* Hard-coding `production_certified=true`  

---

## 13. Proposed bounded implementation

```text
saathi/inference/ops/          # lifecycle service + CLI
docs/evidence/m26/             # ops state, incidents, mode evidence
tests/test_m26_inference_operations.py
python -m saathi.inference.ops <cmd>
```

Default mode: **OFF**. ACTIVE requires valid production certification from runtime_gate / package evidence (computed, not forced).
