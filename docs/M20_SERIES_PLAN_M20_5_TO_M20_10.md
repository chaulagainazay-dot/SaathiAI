# M20 Series Plan — M20.5 through M20.10 (Closure Path)

**Status:** Authorized product plan (not auto-executed as a single unattended block).  
**Rule:** One milestone per autonomous iteration unless the user explicitly authorizes multi-milestone work.  
**Master loop:** `docs/M20_MASTER_AUTONOMOUS_ENGINEERING_LOOP.md`

| ID | Title | Intent | Depends on | Default posture |
|----|-------|--------|------------|-----------------|
| **M20.5** | Canonical Engineering Session Ledger, Integrity Evidence, and Recovery | Durable session event ledger + integrity evidence chain + crash/stale recovery — **not** a second harness run ledger | M20.0, M20.4 | Off / local store |
| **M20.6** | Live Local Inference Certification on an Installed Small Model | Honest live cert only if Ollama + ≤3B model already installed; no download | M20.2, M20.3 | Off; BLOCKED_ENVIRONMENT if missing |
| **M20.7** | Engineering Orchestrator and Inference Runtime Consolidation | Shared observability, flags, CLI discovery; no merge of domains; no second gateways | M20.0–M20.5 | Defaults unchanged |
| **M20.8** | Bounded Additional Caller Adoption and Shadow Evaluation | At most 1–2 new low-risk callers; shadow-first; chat still legacy | M20.3 | legacy default |
| **M20.9** | M20 Integration, Regression, Security, and Resource Certification | Cross-package tests, TG isolation, resource budget on 8 GB | M20.0–M20.8 | Evidence-only |
| **M20.10** | M20 Closure, Operational Runbook, and M21 Handoff | Freeze M20 surface, full runbook, explicit M21 options | M20.9 | Series closed |

## Non-goals (entire remainder of M20)

* Global chat migration  
* Production unattended engineering  
* Force-push / merge / deploy automation  
* Trading Guardian engagement  
* OpenJarvis process runtime  
* Automatic model download / 8B default on 8 GB Mac  
* Replacing Mission Engine, ExecutionGateway, ModelRouter, or harness run ledger  

## Execution order

```text
M20.5 (this iteration when authorized)
  → M20.6 (only if environment can support live small model, else document BLOCKED_ENVIRONMENT and continue)
  → M20.7 consolidation
  → M20.8 optional callers
  → M20.9 certification
  → M20.10 closure + M21 handoff
```

## Success for series close (M20.10)

* All M20 pilots remain disabled by default  
* Durable engineering session evidence + recovery proven  
* Inference opt-in path documented; live cert honest  
* Integration/security/TG evidence recorded  
* Operator runbook + M21 candidates without auto-start  

---

*M20.5 implementation details live in `docs/M20_5_*` once the slice lands.*
