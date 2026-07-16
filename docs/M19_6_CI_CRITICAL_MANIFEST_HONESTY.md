# M19.6 — CI Critical Manifest Environment Honesty

## Problem

GitHub Actions `reliability` on `ubuntu-latest` failed Critical Manifest with:

| Check | Root cause class |
|-------|------------------|
| `studio.studio_os_m13` | Environmental: `test_quota_enforced` used 50 GB estimate; host free disk raised `InsufficientDisk` before `QuotaExceeded` |
| `security.redteam_*` / `computer.redteam` / `computer.cdp_loopback` | Environmental misclassified as vuln: probes `SQLITE-TWOAPP-001` / `JQ-THREEAPP-001` required ffmpeg on PATH |
| `native.perm_honest` | Schema gap: non-macOS `summary()` omitted readiness keys |
| `sqlite.two_live_apps` / `jq.three_live_apps` | Environmental: asserted ffmpeg executable regardless of host |

Local macOS (ffmpeg present, ample disk) stayed green — failures were CI-environment honesty, not product security regressions.

## Fix (bounded)

1. **Quota test** — monkeypatch `free_gb` so quota failure is independent of host free space.
2. **Native summary** — always emit `native_accessibility_ready` / `native_actuation_ready` / `screen_recording_ready` (False on non-macOS).
3. **Multi-app tests + redteam probes** — require only host-available pilot binaries; missing ffmpeg is env-blocked, not confirmed vulnerability.
4. **CI workflow** — install `ffmpeg`, `jq`, `sqlite3` so multi-app live path still exercises when possible.

## Out of scope

* Merge to main / deploy / release
* Weakening security probes that hold on macOS
* Live trading / Trading Guardian
* InsForge expansion
* Full suite redesign

## Security analysis

* No approval / ExecutionGateway / tenant isolation changes.
* Redteam still fails closed on real boundary failures (`boundary_held=False`).
* Does not hide failures with unconditional skips of security corpus.
* Installs only public apt packages in CI; no secrets.

## Acceptance

* [x] `test_quota_enforced` passes with simulated low free disk scenario (monkeypatched ample free + large estimate → QuotaExceeded)
* [x] Non-macOS summary includes readiness keys all False
* [x] Without ffmpeg, SQLITE/JQ multi-app probes hold with honest notes
* [x] With ffmpeg, multi-app probes still require full live set
* [x] Full deterministic redteam: 0 confirmed / 0 release-blocking
* [x] Trading Guardian untouched

## Rollback

```bash
git revert <this-commit>
# or restore previous reliability.yml + probes + tests
```

## Disable

N/A (test/CI honesty only). Optional: remove apt install step without losing test honesty.

## Verdict

**CI CRITICAL MANIFEST ENVIRONMENT HONESTY READY** — not a product capability promotion; not production-ready claim.
