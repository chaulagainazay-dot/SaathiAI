# M20.10 — M20 Closure, Operational Runbook, and M21 Handoff

**Series close date:** 2026-07-16  
**Branch:** `milestone/m7-security-engine`  
**M20.9 commit:** `815175a`  
**Final series posture:** Pilot platform closed with explicit limitations  

---

## 1. Canonical M20 milestone map

| ID | Title | Status | Evidence |
|----|-------|--------|----------|
| M20.0 | Governed Engineering Orchestrator | COMPLETE (pilot) | `docs/M20_0_*`, tests |
| M20.1 | Local inference runtime (OJ concepts) | COMPLETE (pilot) | `docs/M20_1_*` |
| M20.2 | Governed local inference path | COMPLETE (pilot) | `docs/M20_2_*` |
| M20.3 | Opt-in LLM caller migration (2 callers) | COMPLETE (pilot) | `docs/M20_3_*` |
| M20.4 | Control Center + RO agent sessions | COMPLETE (pilot) | `docs/M20_4_*` |
| M20.5 | Session ledger, integrity, recovery | COMPLETE (pilot) | `docs/M20_5_*` |
| M20.6 | Live local model certification | **BLOCKED** (environment) | `docs/M20_6_*` |
| M20.7 | Orchestrator + inference console consolidation | COMPLETE (obs) | `docs/M20_7_*` |
| M20.8 | Bounded additional callers | **INTENTIONALLY_SKIPPED** | `docs/M20_8_STATUS.md` |
| M20.9 | Final certification | COMPLETE WITH LIMITATIONS | `docs/M20_9_*` |
| M20.10 | Closure + M21 handoff | **THIS DOCUMENT** | |

Master loop: `docs/M20_MASTER_AUTONOMOUS_ENGINEERING_LOOP.md`  
Series plan: `docs/M20_SERIES_PLAN_M20_5_TO_M20_10.md`

---

## 2. What M20 delivered (honest)

### Engineering pilot
* Disabled-by-default orchestrator over coding-agent work  
* Deterministic selection, readiness, bounded prompts  
* Mock + Claude adapters; RO approvals; integrity; quarantine  
* Session ledger (hash chain), recovery (no auto-launch)  
* Control Center engineering facet  

### Inference pilot
* SaathiOS-native inference package (not OJ process)  
* Governed gateway path via ModelRouter  
* Opt-in modes for `cheap_ask` and `prose_clean` only (default **legacy**)  
* Certification suite ready; **live model not certified on pilot host**  

### Console
* Read-only aggregation (`saathi.m20_console`) — not a new authority  

### Explicit non-deliveries
* Global chat / voice / IELTS migration  
* Write-enabled autonomous engineering in production  
* Live Ollama generation proof on this Mac  
* Merge/deploy/release automation  
* Trading Guardian engagement  

---

## 3. Architecture freeze (M20 surface)

```text
saathi.engineering     — orchestration, ledger, integrity, RO sessions
saathi.inference       — runtime, gateway path, rollout, cert
saathi.m20_console     — read-only flags/status/discover/disable
```

Authority boundaries certified in M20.9 tests. Do not merge stores or routers.

---

## 4. Readiness classification

| Capability | Level | Notes |
|------------|-------|-------|
| Eng orchestrator (default-off) | pilot / deterministic-tested | Not production |
| RO supervised sessions | pilot / mock-proven | Writes remain off |
| Session ledger + recovery | pilot / deterministic-tested | Not harness run_ledger |
| Governed inference path | pilot / default-off | Needs live engine for ops use |
| Opt-in callers (2) | pilot / legacy default | No extra M20.8 callers |
| Live ≤3B local cert | **blocked** | Install Ollama+model manually |
| M20 console | pilot / read-only | Observability only |
| Production deploy | **not ready** | — |
| Live trading | **not in scope / unengaged** | TG isolated |

---

## 5. Operational runbook (summary)

Full flag disable: `python -m saathi.m20_console disable`

```bash
# Status
python -m saathi.m20_console status
python -m saathi.m20_console flags
python -m saathi.engineering status
python -m saathi.inference.certification discover

# Engineering (still default-off)
python -m saathi.engineering control-center
python -m saathi.engineering ledger
python -m saathi.engineering recover --dry-run

# Cert (live only if model installed)
python -m saathi.inference.certification run
```

Disable all:

```bash
unset SAATHI_ENG_ORCH_ENABLED SAATHI_ENG_ORCH_LAUNCH \
      SAATHI_ENG_ORCH_WRITES SAATHI_ENG_ORCH_COMMITS SAATHI_ENG_ORCH_PUSHES
unset SAATHI_INFERENCE_ENABLED SAATHI_INFERENCE_GATEWAY_ENABLED \
      SAATHI_ALLOW_CLOUD_FALLBACK \
      SAATHI_INF_ROLLOUT SAATHI_INF_ROLLOUT_CHEAP_ASK SAATHI_INF_ROLLOUT_PROSE_CLEAN
```

---

## 6. Recertification runbook

Re-run when host changes or models install:

1. `git status -sb` clean on pilot branch  
2. `pytest tests/test_m20_9_final_certification.py tests/test_m20_7_console_consolidation.py -q`  
3. `python -m saathi.inference.certification run` — expect COMPLETE only if live model works  
4. Update `docs/M20_6_LIVE_CERT_RESULT.md` only with real live output  
5. Never re-label BLOCKED as COMPLETE without live evidence  

---

## 7. Technical debt (closed series)

| Debt | Class |
|------|-------|
| M20.6 live model blocked | environment |
| M20.8 not executed | intentional skip |
| No unified eng/inf metrics DB | deferred |
| Write-enabled eng autonomy | future governed milestone |
| Chat default migration | deferred / out of M20 |
| Full monorepo suite every slice | operational |

---

## 8. Rollback (newest first)

```bash
git revert <M20.10-sha>   # this closure commit
git revert 815175a        # M20.9
# earlier pilots as needed: 947d267, 94808eb, ...
```

---

## 9. M21 handoff (do not auto-start)

### Recommended title
**M21 — Revenue-Path Productization of Governed Pilots** (or operator rename)

### First bounded milestone candidates (pick one)
1. **M21.0** Unblock live local inference (operator installs ≤3B) + re-run M20.6 cert → shadow one caller  
2. **M21.0** Production-safe packaging of M20 console + disable drills for operator onboarding  
3. **M21.0** One revenue-adjacent product slice that **reuses** gateway/orchestrator without expanding autonomy  

### Reuse from M20
Orchestrator, ledger, integrity, RO approvals, inference path, rollout, console, cert suite  

### Remaining prohibitions into M21
No silent global chat switch; no TG crossover; no force-push/merge/deploy without explicit auth; no auto model download  

### Exact next operator decision
Choose M21.0 focus (live model unblock vs productization vs revenue feature) **before** any agent starts M21.

### M21 started?
**No.**

---

## 10. Final M20 verdict

```text
M20 COMPLETE WITH LIMITATIONS — PILOT PLATFORM CLOSED; LIVE LOCAL INFERENCE REMAINS ENVIRONMENT-BLOCKED
```
