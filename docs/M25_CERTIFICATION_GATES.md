# M25 Certification Gates

See also: `docs/M25_PRODUCTION_CERTIFICATION.md` (final architecture).

## Production-safe memory

```text
available_memory_gb >= safety_margin_gb + minimum_model_budget_gb
# 1.5B: 0.8 + 1.0 = 1.8 GB free required
```

## Live vs production

| Gate | Meaning |
|------|---------|
| live_provider_certified | Real local non-stream path passed (historical dual-evidence) |
| production_certified | All mandatory runtime_gate checks PASS including package evidence |

## Package evidence states

| State | Meaning |
|-------|---------|
| PASS | Artifact present, fingerprint matches, not expired, status PASS |
| STALE | Fingerprint mismatch or past `expires_at` |
| FAIL | Producer recorded failure |
| MISSING | No artifact on disk |

## Evidence

| File | Semantics |
|------|-----------|
| LAST_SUCCESSFUL_LIVE_CERTIFICATION.json | Historical PASS; not erased by blocked re-runs |
| LATEST_ENVIRONMENT_OBSERVATION.json | Current host snapshot |
| LIVE_CERT_EVIDENCE.json | Combined view |
| cert/full_suite_evidence.json | Canonical full suite |
| cert/secret_scan_evidence.json | Canonical secret scan |
| cert/critical_check_evidence.json | Canonical critical checks |
| cert/certification_package.json | Package summary |

## Blockers

| Code | Meaning |
|------|---------|
| insufficient_model_memory_headroom | Model installed; free RAM below formula |
| no_installed_models_observed | No models |
| embedding_model_missing | Ollama up but embed model absent (memory auto path) |
| full_suite_evidence:STALE/MISSING | Re-run `cert_evidence record-package` |
| secret_scan_evidence:FAIL | Strong credential hit |
| critical_check_evidence:FAIL | Blocking critical check failed |
