# M25 Production Certification Architecture

Final closeout of M25: convert already-passing repository evidence into
**canonical production-certification artifacts** consumed by `runtime_gate`.

## Verdict model

```text
production_certified = true
  iff every MANDATORY_CERT_CHECK is GateState.PASS
  (including live_provider_cert + package evidence)
```

Otherwise `production_certified = false` with an exact `certification_blockers`
list (`check_id:STATE`). No ambiguous middle state.

## Components

| Component | Module / path |
|-----------|----------------|
| Package evidence store | `saathi/inference/cert_evidence.py` |
| Runtime gate | `saathi/inference/runtime_gate.py` |
| Live dual evidence | `saathi/inference/live_cert_m25.py` |
| Release check | `saathi/inference/release_check.py` |
| Secret scan | `saathi/repair/secrets_scan.py` |
| Critical checks | `saathi/repair/critical_checks.json` + `manifest` / `verify` |
| Artifacts | `docs/evidence/m25/cert/*.json` |

## Evidence map

| Evidence name | Producer | Current location | Certification location | Fingerprint | Freshness |
|---------------|----------|------------------|------------------------|-------------|-----------|
| full_suite_evidence | `cert_evidence.record_full_suite` | pytest log / explicit counts | `docs/evidence/m25/cert/full_suite_evidence.json` | `package_fingerprint()` | TTL 14d; STALE on fp mismatch |
| secret_scan_evidence | `cert_evidence.record_secret_scan` | strong-credential scan | `docs/evidence/m25/cert/secret_scan_evidence.json` | same | same |
| critical_check_evidence | `cert_evidence.record_critical_checks` | critical manifest + server.import | `docs/evidence/m25/cert/critical_check_evidence.json` | same | same |
| focused_suite_evidence | `cert_evidence.record_focused_suite` | m25+memory pytest | `docs/evidence/m25/cert/focused_suite_evidence.json` | same | same (informational) |
| live historical PASS | `live_cert_m25` | last successful live run | `docs/evidence/m25/LAST_SUCCESSFUL_LIVE_CERTIFICATION.json` | model id in package fp | not erased by RAM drop |
| live latest observation | `live_cert_m25` | latest discover/run | `docs/evidence/m25/LATEST_ENVIRONMENT_OBSERVATION.json` | n/a (observation) | always overwrite |
| release_check | `release_check.run_release_check` | in-process gate | gate check `release_check` | code identity | run each gate |
| residual / cloud / TG | static gates | residual manifest + settings | gate checks | residual schema | run each gate |

## Evidence lifecycle

```text
operator / CI
  → python -m saathi.inference.cert_evidence record-package [--from-log PATH | --passed N]
  → atomic JSON write per artifact (tmp + os.replace)
  → certification_package.json summary
  → python -m saathi.inference.runtime_gate
       loads disk artifacts (unless keys overridden)
       maps PASS | FAIL | STALE | MISSING
       decide_production_certified(force_false=False)
```

Each artifact includes: `schema`, `status`, `created_at`, `expires_at`,
`ttl_seconds`, `package_fingerprint`, `tip_commit`, `producer`,
`producer_version`, `detail`, `metrics`, `privacy_safe`.

## Fingerprint policy

`package_fingerprint()` hashes material certification code/policy only:

* runtime_gate, release_check, live_cert_m25, cert_evidence
* gateway_path, certification, provider_policy, residual_paths
* residual exception manifest, critical_checks.json
* last successful live model id (if present)

**Does invalidate:** code/policy/schema/model-identity changes.

**Does not invalidate:** temporary RAM drops, discover re-runs, environment
observation updates, non-fingerprint file edits.

## Freshness policy

1. Missing file → `MISSING`
2. Stored status `FAIL` → `FAIL`
3. Fingerprint mismatch vs current → `STALE`
4. `expires_at` in the past → `STALE`
5. Else if stored `PASS` → `PASS`

Default TTL: **14 days**.

## Production decision flow

```text
evaluate_runtime_gate
  merge disk package evidence (unless _skip_disk_cert_evidence)
  run static + live + package checks
  decide_production_certified(checks, force_false=False)
  production_certified = (no blockers)
  certification_blockers = exact list
```

Mandatory package states are never collapsed from STALE/MISSING/NOT_TESTED to PASS.

## Operator workflow

```bash
# 1) After a green full suite, package evidence
.venv/bin/python -m saathi.inference.cert_evidence record-package \
  --from-log /path/to/pytest.log
# or: --passed 3095 --failed 0 --skipped 1

# 2) Inspect
.venv/bin/python -m saathi.inference.cert_evidence status
.venv/bin/python -m saathi.inference.runtime_gate --json

# 3) If STALE (code change), re-run record-package

# 4) Do not start M26 until operator authorizes
```

## Invariants

```text
Residual inference exceptions = 0
Cloud fallback = disabled
Live provider route = governed
Trading Guardian = UNCHANGED / UNENGAGED
Historical live PASS preserved under dual-evidence model
```

## Dual evidence vs package evidence

| Layer | Purpose |
|-------|---------|
| Historical live | Proves real transport once worked; survives MEMORY_BLOCKED re-observe |
| Latest environment | Current RAM/model/daemon observation |
| Package evidence | Suite + secret scan + critical checks for production claim |

Live gate may report `historical=PASS` and `current=ENVIRONMENT_BLOCKED`
simultaneously; package suite is independent of RAM.
