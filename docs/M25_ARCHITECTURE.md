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
→ M25 evidence bundle
```

## Harness

| Component | Module |
|-----------|--------|
| Environment discovery | `saathi.inference.live_cert_m25.discover_environment` |
| Certification run | `saathi.inference.live_cert_m25.run_m25_certification` |
| Evidence | `docs/evidence/m25/LIVE_CERT_EVIDENCE.json` |
| Runtime gate | `m25_live_provider_cert`, `m25_no_mock_as_live`, production invariants |
| Prior suite | `saathi.inference.certification` (M20.6) reused for engine/model discovery |

## Invariants

* Mock / unit success is never labelled `live=true` / `live_provider_certified=true`.
* `production_certified=true` only when live cases pass **and** all mandatory gates pass.
* No install, no pull, no cloud, no credentials.
* M22 adapters, M23 chat, M24 durable governance preserved.

## This host

Live path **ENVIRONMENT_BLOCKED** — see environment audit.
