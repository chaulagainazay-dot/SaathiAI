# M25 Architecture — Live Local Provider Certification

## Certification path (when environment ready)

```text
caller
→ canonical InferenceRequest
→ durable reservation (zero-cost local)
→ durable circuit check
→ ModelRouter
→ governed Ollama adapter
→ real local transport
→ typed result / stream events
→ durable settlement
→ M25 live evidence bundle
→ package evidence (suite / secret / critical)
→ runtime_gate decide_production_certified
```

## Harness

| Component | Module |
|-----------|--------|
| Environment discovery | `saathi.inference.live_cert_m25.discover_environment` |
| Certification run | `saathi.inference.live_cert_m25.run_m25_certification` |
| Live evidence | `docs/evidence/m25/LIVE_CERT_EVIDENCE.json` (+ dual files) |
| Package evidence | `saathi.inference.cert_evidence` → `docs/evidence/m25/cert/` |
| Runtime gate | `m25_live_provider_cert`, package checks, production decision |
| Prior suite | `saathi.inference.certification` (M20.6) reused for engine/model discovery |

## Final certification architecture

Documented in **`docs/M25_PRODUCTION_CERTIFICATION.md`**:

* Evidence lifecycle (atomic JSON, schema, TTL, fingerprint)
* Fingerprint policy (code/policy/model — not RAM)
* Freshness (PASS / STALE / FAIL / MISSING)
* Production decision flow
* Operator workflow

## Invariants

* Mock / unit success is never labelled `live=true` / `live_provider_certified=true`.
* `production_certified=true` only when every mandatory runtime_gate check is PASS
  (historical live + full suite + secret scan + critical checks + static gates).
* No install, no pull, no cloud, no credentials as part of M25 closeout automation.
* M22 adapters, M23 chat, M24 durable governance preserved.
* Trading Guardian unchanged / unengaged.

## This host

Historical live **PASS** preserved. Current environment may be
`ENVIRONMENT_BLOCKED` under memory pressure without invalidating package or
historical live evidence.
