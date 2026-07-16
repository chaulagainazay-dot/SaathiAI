# M21–M39 Master Program Roadmap (Canonical Platform)

**Authority:** SaathiAI monorepo platform roadmap for production-controlled release  
**Initialized:** 2026-07-16 from HEAD `44f263a`  
**Companion docs:** `docs/M21_39_MASTER_PROGRAM_AUDIT.md`, `docs/M21_39_GATE_MATRIX.md`  
**Does not replace:** M1–M20 historical labels; pielts **PRODUCT/IELTSAlert** numbering in the product repo  

---

## 0. Numbering namespaces

| Namespace | Scope | Example |
|-----------|--------|---------|
| **Platform (this repo)** | SaathiOS monorepo M21–M39 | M21 Runtime Consolidation |
| **PRODUCT/IELTSAlert** | `/Users/macbookpro/Saathi/apps/pielts` | PRODUCT M21.0 revenue foundation |
| **M20.10 options** | Historical handoff choices | Remapped below — not active IDs |

### Remap of M20.10 handoff options

| Option | Maps to |
|--------|---------|
| A — Unblock ≤3B local model | Operator environment unlock; evidence for M21/M24 — not full M21 alone |
| B — Operator packaging / disable drills / CI | **M21.0** first platform implementation slice |
| C — One product feature via gateway | **M30** or PRODUCT track — not M21 runtime |

---

## 1. Program objective (summary)

Advance from M20 pilot platform to:

1. **CORE RUNTIME PRODUCTION CERTIFIED** (M21–M24)  
2. **GOVERNED AGENT EXECUTION CERTIFIED** (M25–M27)  
3. **SAATHIOS STUDIO OPERATIONAL** (M28–M30)  
4. **CONTROLLED PUBLIC BETA APPROVED** (M31–M33)  
5. Final launch gate M34–M39 with only allowed verdicts:

```text
GO LIVE APPROVED — CONTROLLED RELEASE
STAGING CERTIFIED — PRODUCTION BLOCKERS REMAIN
NOT READY — CRITICAL GAPS REMAIN
```

---

## 2. Phase map (canonical)

### Phase 1 — Production Core Runtime

| ID | Title | Status | Entry criteria | Exit verdict target |
|----|-------|--------|----------------|---------------------|
| **M21** | Runtime Consolidation and Production Configuration | **IN PROGRESS** — **M21.0 COMPLETE** | M20 closed; audit done | `M21 COMPLETE — RUNTIME CONFIGURATION AND MODEL ROUTING CONSOLIDATED` |
| **M22** | Voice, Durable Agents, Recovery, and Observability | NOT STARTED | M21 complete or WITH LIMITATIONS accepted | `M22 COMPLETE — VOICE AND DURABLE AGENT EXECUTION CERTIFIED` |
| **M23** | Multi-User Identity, Isolation, Permissions, and Security | NOT STARTED | M22 complete / accepted limitations | `M23 COMPLETE — MULTI-USER CORE SECURITY AND ISOLATION CERTIFIED` |
| **M24** | Core Runtime Staging and Production Certification | NOT STARTED | M21–M23 evidence present | `CORE RUNTIME PRODUCTION CERTIFIED` **or** `CORE RUNTIME STAGING CERTIFIED — PRODUCTION BLOCKERS REMAIN` |

### Phase 2 — Governed Real-World Execution

| ID | Title | Status | Depends on |
|----|-------|--------|------------|
| **M25** | Governed Tool and External-Action Gateway | NOT STARTED | Prefer M24 staging cert |
| **M26** | Browser, Files, Gmail, Calendar, GitHub, Research Execution | NOT STARTED | M25 |
| **M27** | Automation Engine, CEO OS Execution, Trading Guardian Certification | NOT STARTED | M25–M26 |

**Phase exit:** `GOVERNED AGENT EXECUTION CERTIFIED`

### Phase 3 — SaathiOS Studio

| ID | Title | Status | Depends on |
|----|-------|--------|------------|
| **M28** | Governed AI Studio and Media Job Architecture | NOT STARTED | Prefer Phase 2 for consequential media side effects |
| **M29** | Voice, Video, FFmpeg, Thumbnail, and Marketing Production | NOT STARTED | M28 |
| **M30** | Product Automation (IELTSAlert, Travel, Consultancy, Cafeteria) | NOT STARTED | M28–M29; may coordinate with PRODUCT/IELTSAlert repo |

**Phase exit:** `SAATHIOS STUDIO OPERATIONAL`

### Phase 4 — Public Platform

| ID | Title | Status |
|----|-------|--------|
| **M31** | Authentication, Organizations, Teams, Permissions, and Tenancy | NOT STARTED |
| **M32** | Billing, Plugins, Backups, Updates, Audit, and Deployment Operations | NOT STARTED |
| **M33** | Platform Staging, Controlled Beta, and Public-Platform Readiness | NOT STARTED |

**Phase exit:** `CONTROLLED PUBLIC BETA APPROVED`

### Final Certification

| ID | Title | Status |
|----|-------|--------|
| **M34** | Complete Architecture and Dependency Audit | NOT STARTED |
| **M35** | Penetration, Abuse, Isolation, and Adversarial Testing | NOT STARTED |
| **M36** | Load, Endurance, Concurrency, Reliability, and Cost Testing | NOT STARTED |
| **M37** | Backup, Restore, Disaster Recovery, and Upgrade Rollback | NOT STARTED |
| **M38** | Multi-Device and Real-User Controlled Pilot | NOT STARTED |
| **M39** | Final Production Certification and Controlled Launch | NOT STARTED |

---

## 3. M21 decomposition (when implementation starts)

Do **not** implement all of M21 in one invocation. Suggested slices:

| Slice | Scope | Notes |
|-------|--------|------|
| **M21.0** | Inventory residual inference/call paths; production config schema; provider policy doc + tests; kill-switch matrix extension | Preferred first code milestone (aligns with M20.10-B) |
| **M21.1** | Canonical request contract enforcement; no direct caller→provider | Extend `saathi.inference`, not a second router |
| **M21.2** | Cost metadata, availability state, failover taxonomy | Safe defaults; unsupported disabled |
| **M21.3** | Production configuration gate + Critical Manifest / release-check hooks | Fail closed |
| **M21.x** | Closure + validation docs | Honest evidence tiers |

**Reuse only:** `ModelRouter`, `saathi.inference`, ExecutionGateway/ModelGateway path, `m20_console` flags.  
**Do not create:** second ModelRouter, second inference package, second cost authority.

---

## 4. Global execution rules (carry-forward)

- One milestone or bounded repair per invocation  
- Every capability independently auditable, testable, disableable, rollbackable  
- No production deploy / main merge / force-push without explicit authorization  
- No secrets in git; no uncontrolled paid API; no auto model download  
- No real email/trade/payment in engineering tests without approval  
- Trading Guardian: no bypass; no withdrawal; leverage default-off  
- Prefer extend → migrate → deprecate → guard  

---

## 5. Current pointer

| Field | Value |
|-------|--------|
| Program phase | Phase 1 — M21 in progress |
| Active platform milestone | **M21.0 COMPLETE**; do not auto-start M21.1 |
| Last checkpoint | M21.0 production-config inventory + provider policy |
| Recommended next | **M21.1** request contract enforcement / residual path controls |
| M20.6 live model | Still **ENVIRONMENT_BLOCKED** until operator installs Ollama + ≤3B |

---

## 6. Success criteria (program complete)

Only when M21–M33 complete with evidence, M34–M38 pass, and M39 receives explicit launch authorization, with monitoring, IR, backups, tenant isolation, TG governance, cost ceilings, kill switches, and rollback verified, may the program return:

```text
SAATHIOS M21–M39 COMPLETE
GO LIVE APPROVED — CONTROLLED RELEASE
```

Until then use partial or blocked status only.
