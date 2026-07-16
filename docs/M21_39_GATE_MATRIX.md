# M21–M39 Gate Matrix

**Purpose:** Independent audit gates per milestone — what must be true to claim COMPLETE, WITH LIMITATIONS, PARTIAL, BLOCKED, or FAILED.  
**Evidence rule:** Every claim uses an explicit tier (`SOURCE_INSPECTED`, `UNIT_TESTED`, `INTEGRATION_TESTED`, `EMULATOR_TESTED`, `BROWSER_TESTED`, `STAGING_TESTED`, `PRODUCTION_SMOKE_TESTED`, `ENVIRONMENT_BLOCKED`, `NOT_TESTED`).  
**Never convert:** mock → live certified; focused tests → full suite green; implemented → production ready.

---

## Gate status legend

| Status | Meaning |
|--------|---------|
| OPEN | Milestone not started |
| IN_PROGRESS | Bounded work active |
| COMPLETE | Exit criteria met with required evidence tiers |
| COMPLETE_WITH_LIMITATIONS | Exit criteria met except documented env/license limits |
| PARTIAL | Material progress; exit criteria not met |
| BLOCKED | Cannot proceed without external/operator action |
| FAILED | Attempted; verification failed |

---

## Phase 1 gates

### M21 — Runtime Consolidation and Production Configuration

| Gate ID | Requirement | Min evidence | Status |
|---------|-------------|--------------|--------|
| M21-G1 | One canonical inference request contract | UNIT + integration on path | OPEN (M21.1) |
| M21-G2 | One canonical model-selection path (`ModelRouter`) | SOURCE + tests; no second router | **COMPLETE** (asserted M21.0; pre-existing) |
| M21-G3 | One canonical provider registry | UNIT | **PARTIAL** (M21.0 policy table; engine registry pre-existing) |
| M21-G4 | One canonical execution policy for inference | UNIT | **PARTIAL** (M21.0 policy + settings validator) |
| M21-G5 | No new direct caller→provider paths; inventory residual legacy | SOURCE inventory + guards | **PARTIAL** (inventory COMPLETE; migration → M21.1) |
| M21-G6 | No silent cloud escape (default-off cloud) | UNIT negative tests | **PARTIAL** (policy default off + cloud warning) |
| M21-G7 | Local/cloud policies explicit | SOURCE + UNIT | **COMPLETE** (M21.0) |
| M21-G8 | Streaming/tool capability explicit on contract | UNIT | **PARTIAL** (policy rows; full contract → M21.1) |
| M21-G9 | Timeout and token limits explicit | UNIT | **PARTIAL** (validator caps; settings pre-existing) |
| M21-G10 | Cost ceilings / cost metadata | UNIT | **PARTIAL** (M21.0 cost placeholders; ceilings → M21.2) |
| M21-G11 | Provider health / availability state | UNIT | **PARTIAL** (M21.0 policy availability; live health → M21.2) |
| M21-G12 | Per-provider kill switches | UNIT + disable procedure | **COMPLETE** (M21.0) |
| M21-G13 | Failover taxonomy deterministic | UNIT | OPEN |
| M21-G14 | Production configuration validation gate | UNIT + release-check hook | **PARTIAL** (M21.0 validator; release-check → M21.3) |
| M21-G15 | Privacy-safe metrics | SOURCE + UNIT | OPEN |
| M21-G16 | Trading Guardian unengaged by M21 changes | UNIT isolation | **COMPLETE** (M21.0 isolation test) |
| M21-G17 | Rollback + disable documented | SOURCE | **COMPLETE** (M21.0) |

**Exit verdict forms:**

```text
M21 COMPLETE — RUNTIME CONFIGURATION AND MODEL ROUTING CONSOLIDATED
M21 COMPLETE WITH LIMITATIONS — …
M21 PARTIAL — …
M21 BLOCKED — …
M21 FAILED — …
```

### M22 — Voice, Durable Agents, Recovery, Observability

| Gate ID | Requirement | Min evidence | Status |
|---------|-------------|--------------|--------|
| M22-G1 | STT / TTS contracts | UNIT | OPEN |
| M22-G2 | Barge-in, cancellation, turn-taking | UNIT (+ device if available) | OPEN |
| M22-G3 | Audio device recovery | UNIT / env-honest | OPEN |
| M22-G4 | Durable agent sessions + checkpoints + leases | INTEGRATION | OPEN |
| M22-G5 | Restart recovery without duplicate side effects | INTEGRATION | OPEN |
| M22-G6 | Stall detection + alerting | UNIT/INTEGRATION | OPEN |
| M22-G7 | Idempotency + event replay + run reconciliation | INTEGRATION | OPEN |
| M22-G8 | Operator stop | UNIT | OPEN |
| M22-G9 | Cost/latency monitoring (privacy-safe) | UNIT | OPEN |
| M22-G10 | Required negative/interruption matrix | tests listed in program §10 | OPEN |

### M23 — Multi-User Isolation and Security

| Gate ID | Requirement | Min evidence | Status |
|---------|-------------|--------------|--------|
| M23-G1 | Canonical identity / org / workspace / project | UNIT | OPEN |
| M23-G2 | Roles + capabilities + ownership | UNIT | OPEN |
| M23-G3 | Tenant isolation (memory/file/browser/cred/approval) | INTEGRATION negative suite | OPEN |
| M23-G4 | Session ownership + expiration + revocation | UNIT | OPEN |
| M23-G5 | Admin boundaries; no self-grant admin | negative UNIT | OPEN |
| M23-G6 | Confused-deputy / replay / stale token | negative UNIT | OPEN |
| M23-G7 | Audit attribution | UNIT | OPEN |

### M24 — Core Runtime Staging / Production Certification

| Gate ID | Requirement | Min evidence | Status |
|---------|-------------|--------------|--------|
| M24-G1 | Dedicated staging environment | STAGING_TESTED or BLOCKED honest | OPEN |
| M24-G2 | Authorized real provider smoke | STAGING or ENVIRONMENT_BLOCKED | OPEN |
| M24-G3 | Full runtime integration suite | INTEGRATION | OPEN |
| M24-G4 | Voice device/browser tests | BROWSER/device or honest block | OPEN |
| M24-G5 | Agent recovery tests | INTEGRATION | OPEN |
| M24-G6 | Multi-user isolation tests | INTEGRATION | OPEN |
| M24-G7 | Cost-limit tests | UNIT/INTEGRATION | OPEN |
| M24-G8 | Monitoring + alerts + backup + rollback | STAGING or drill | OPEN |
| M24-G9 | Incident runbook + security review | SOURCE | OPEN |
| M24-G10 | Controlled canary (if authorized) | STAGING/PRODUCTION_SMOKE or not claimed | OPEN |

**Allowed M24 phase verdicts:**

```text
CORE RUNTIME PRODUCTION CERTIFIED
CORE RUNTIME STAGING CERTIFIED — PRODUCTION BLOCKERS REMAIN
```

---

## Phase 2 gates (summary)

| Milestone | Key gates | Status |
|-----------|-----------|--------|
| **M25** | Intent→actor→capability→policy→risk→approval→idempotency→exec→evidence→reconcile→audit; tool classes; registry; circuit breaker; kill switch | OPEN |
| **M26** | Browser/files/Gmail/Calendar/GitHub/research each class governed; credentials env-honest | OPEN |
| **M27** | Automation + CEO OS governed; **TG certified isolated**; no live trade without auth; no withdrawal | OPEN |

**Phase verdict:** `GOVERNED AGENT EXECUTION CERTIFIED`

---

## Phase 3 gates (summary)

| Milestone | Key gates | Status |
|-----------|-----------|--------|
| **M28** | Studio/media jobs under gateway; no second studio engine | OPEN |
| **M29** | Voice/video/FFmpeg/thumbnail/marketing production path; cost ceilings | OPEN |
| **M30** | IELTSAlert/Travel/Consultancy/Cafeteria automation; coordinate PRODUCT namespace | OPEN |

**Phase verdict:** `SAATHIOS STUDIO OPERATIONAL`

---

## Phase 4 gates (summary)

| Milestone | Key gates | Status |
|-----------|-----------|--------|
| **M31** | Auth/orgs/teams/roles/tenancy | OPEN |
| **M32** | Billing/plugins/backups/updates/audit/deploy ops | OPEN |
| **M33** | Controlled beta readiness | OPEN |

**Phase verdict:** `CONTROLLED PUBLIC BETA APPROVED`

---

## Final certification gates (summary)

| Milestone | Key gates | Status |
|-----------|-----------|--------|
| **M34** | Architecture + dependency audit clean of duplicate authorities | OPEN |
| **M35** | No open critical/high pen/abuse/isolation findings | OPEN |
| **M36** | Load/endurance/concurrency/reliability/cost envelope | OPEN |
| **M37** | Backup/restore/DR/upgrade rollback proven | OPEN |
| **M38** | Multi-device + real-user controlled pilot | OPEN |
| **M39** | Explicit launch authorization + ops readiness | OPEN |

**M39 allowed launch verdicts only:**

```text
GO LIVE APPROVED — CONTROLLED RELEASE
STAGING CERTIFIED — PRODUCTION BLOCKERS REMAIN
NOT READY — CRITICAL GAPS REMAIN
```

---

## Cross-cutting hard gates (every milestone)

| Gate | Rule |
|------|------|
| X-1 | No production deploy without explicit authorization |
| X-2 | No secret commit (`.env`, keys, tokens, cookies, SA JSON) |
| X-3 | No force-push / history rewrite |
| X-4 | No TG kill-switch disable to pass tests |
| X-5 | No uncontrolled paid API / model download |
| X-6 | Disable procedure documented |
| X-7 | Git rollback point recorded |
| X-8 | Full-suite status stated honestly (focused ≠ full) |
| X-9 | Concurrent ownership: stop if exclusive ownership lost |

---

## Program-initialization gates (this checkpoint)

| Gate ID | Requirement | Evidence | Status |
|---------|-------------|----------|--------|
| INIT-G1 | Repository intake recorded | This matrix + audit | **COMPLETE** (`SOURCE_INSPECTED`) |
| INIT-G2 | Milestone number conflicts mapped | Audit §3 | **COMPLETE** |
| INIT-G3 | M21–M39 roadmap published | `M21_39_MASTER_PROGRAM_ROADMAP.md` | **COMPLETE** |
| INIT-G4 | Gate matrix published | this file | **COMPLETE** |
| INIT-G5 | Canonical loop/roadmap state updated | `AUTONOMOUS_*`, HANDOFF, SESSION_STATE | **COMPLETE** (with commit of this checkpoint) |
| INIT-G6 | No platform M21 code claimed | Audit §8 | **COMPLETE** — implementation not started |

```text
PROGRAM INIT VERDICT: M21–M39 PROGRAM INITIALIZED — AUDIT AND ROADMAP ONLY
```
