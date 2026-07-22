# M42 — Graduation Criteria Report

Criteria reuse the M39.3 `graduate_requires_all` / `abort_if_any`. Evidence digest
`6103d6c2…`. **14/14 criteria PASS on content; 1 abort condition present.**

## Graduation criteria (GC-1 … GC-14)

| ID | Criterion | Status | Provenance | Source |
|----|-----------|--------|-----------|--------|
| GC-1 | M40 real-provider live certification passed | PASS | MACHINE_PROOF | m40_live_cert |
| GC-2 | M40 proved real live execution | PASS | MACHINE_PROOF | m40_live_cert |
| GC-3 | External revocation effective (http 401) | PASS | MACHINE_PROOF | m40_revocation |
| GC-4 | Provider github_meta, read-only | PASS | MACHINE_PROOF | m40_live_cert |
| GC-5 | No write operations | PASS | MACHINE_PROOF | m40_live_cert |
| GC-6 | M41 bounded canary completed | PASS* | **OPERATOR_ATTESTED** | m41_bounded_canary |
| GC-7 | No unresolved M39.5 alerts | PASS* | OPERATOR_ATTESTED | m41_bounded_canary |
| GC-8 | No rollback-triggering condition | PASS* | OPERATOR_ATTESTED | m41_bounded_canary |
| GC-9 | Identity + scope stable | PASS* | OPERATOR_ATTESTED | m41_bounded_canary |
| GC-10 | Credential lifecycle closed | PASS* | OPERATOR_ATTESTED | m41_bounded_canary |
| GC-11 | No prohibited authority granted | PASS | MACHINE_PROOF | chain |
| GC-12 | Trading Guardian unengaged | PASS | MACHINE_PROOF | chain |
| GC-13 | M32 CANARY/ACTIVE prohibition unchanged | PASS | MACHINE_PROOF | runtime |
| GC-14 | Kill switch + auto-rollback available | PASS* | OPERATOR_ATTESTED | m41_bounded_canary |

`PASS*` = content passes, but the underlying evidence is **operator-attested**, not
machine-proven. Six criteria (GC-6..GC-10, GC-14) rest on attestation.

## Abort conditions (`abort_if_any`)

| ID | Condition | Present |
|----|-----------|---------|
| **AB-PROV** | M41 bounded-canary completion is operator-attested, not machine-proven | **YES** |
| AB-1..AB-11 | unresolved alert / rollback / identity-scope drift / prohibited grant / missing revocation / lifecycle open / inconsistency / missing evidence / simulated-as-live / TG engaged | no |

## Decision

Content criteria all pass and no operational abort fires — **but** `AB-PROV` is
present. Per fail-closed provenance rules, attestation cannot satisfy a machine-proof
requirement. **Verdict: `GRADUATION_NOT_RECOMMENDED`.**

To reach `GRADUATION_RECOMMENDED`, the operator must produce **machine-verified**
M41 bounded-canary evidence (re-run the bounded canary in-session, capturing machine
evidence as M40 did). No criterion was weakened to force a positive result.
