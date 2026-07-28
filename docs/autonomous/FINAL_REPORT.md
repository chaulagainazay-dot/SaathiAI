# SaathiOS Voice Output Foundation Final Report

Status: complete with limitations.

## 1. Final verdict

`VOICE_FOUNDATION_COMPLETE_WITH_LIMITATIONS`.

SaathiOS now has a bounded, provider-neutral, local-first speech layer. It can
synthesize and play English through the authenticated application path using the
native macOS provider. VoxCPM remains optional and uninstalled. Production use is
not authorized.

## 2. Recovery verification

- Repository path: `/Users/macbookpro/SaathiAI`
- Branch: `milestone/m61-backend-workflow-persistence`
- Expected historical voice baseline (ancestor):
  `7873586aea6066d9e1d51b1d60f85ca413127907` — verified as ancestor
- Session start HEAD (M77 committed):
  `285ffbbaa9d4180301d31bb1cd1a8bd8526e8d1a`
- Pre-existing dirty tree preserved and excluded from commits:
  `docs/evidence/m25`, `docs/evidence/m27`, `docs/evidence/m28`,
  untracked `docs/design-spec/`
- M69–M72 Autonomous Mission Runtime was not restarted or redesigned

## 3. Ending branch/SHA

- Branch unchanged: `milestone/m61-backend-workflow-persistence`
- M78 implementation/evidence commit is recorded at closeout after this report is
  included in the terminal autonomous-state checkpoint.

## 4. Allocated milestones

- M73 — initial audit and machine-fit decision
- M74 — provider-neutral backend, providers, profiles, RBAC/API/evidence/audit
- M75 — unified-shell speech controls
- M76 — IELTS feedback read-aloud
- M77 — resource/security/full regression; browser journey limitation
- M78 — browser re-certification and playback hardening

## 5. Architecture

- Canonical authority: `saathi.platform.voice.SpeechService`
- Provider contract: capabilities, health, synthesis, optional streaming semantics,
  cancellation, shutdown
- Providers: `MacOSSystemSpeechProvider` (certified), `VoxCPMSpeechProvider`
  (adapter only), `UnavailableSpeechProvider`
- Reused authorities: Identity, RBAC, tenancy/workspace, PlatformStore,
  PlatformAgentRuntime, ExecutionGateway, Approval Center, evidence, audit,
  notifications, ModuleRegistry, unified shell, route guards, browser cert harness

## 6. SpeechService and provider contract

Authenticated, tenant-scoped operations with ownership checks, idempotency, bounded
input/queue, concurrency limits, lifecycle, timeouts, cancellation, cleanup, restart
reconciliation, safe fallback, evidence and audit linkage, and truthful error mapping.

## 7. macOS provider status

- Certified for English backend synthesis and browser playback
- Local only; no network
- Safe subprocess argument arrays via `run_bounded`; never `shell=True`
- Default browser path: `say` → AIFF intermediate → `afconvert` WAVE/LEI16@22050
- AIFF remains supported when requested
- Installed voice discovery is single-flight and does not permanently cache failed probes
- No raw private path returned through APIs; no public listener; no main-server blocking

## 8. VoxCPM status

| Gate | Status |
|------|--------|
| Adapter implemented | yes |
| Dependencies installed | no |
| Model installed | no |
| Configured | no |
| Provider healthy | no (disabled) |
| Inference executed | no |
| Quality reviewed | no |
| Certified | no |

Machine-fit: VoxCPM2 Python/MPS not selected for this M2/8 GB host. No package or
model was installed or downloaded.

## 9. Voice profiles and Yeti

Bounded provider-neutral profiles with built-ins `saathi_default` and `yeti_teacher`
(warm, calm, encouraging adult teacher design metadata; not a clone). Rate, language,
style, provider mapping, module/accessibility preferences, tenant ownership, versioning.

## 10. API and frontend behavior

- Authenticated `/api/v1/platform/voice/*` routes
- Speak / Stop / Play (explicit; no autoplay)
- Operation state, provider/fallback display, voice selector, rate control
- Logout and tenant/workspace invalidation clear protected client state
- IELTS uses shared client with feedback-only text and Yeti profile

## 11. Lifecycle, queue, fallback, cancellation, recovery

Persisted states include queued through completed/cancelled/failed/unavailable/expired.
Queue depth 8; heavy-provider concurrency 1; VoxCPM request falls back to macOS when
disabled; cancellation propagates to provider process groups; restart reconciliation
without blind replay.

## 12. Language and cloning

- English: backend + browser certified via macOS
- Nepali: `UNSUPPORTED_NOT_VERIFIED`
- Cloning: `CAPABILITY_DISABLED`

## 13. RBAC, tenancy, evidence, audit

Existing platform RBAC permissions (`voice.read`, `voice.speak`, profile/provider/
reference/clone/audit). Tenant/workspace/owner isolation. Append-only evidence/audit
with no raw text, private paths, or audio bytes in audit records.

## 14. Security findings

No `shell=True`, public listener, hidden download, raw path response, unrestricted
cloning, arbitrary executable/model selection, cross-tenant artifact access, or
authorization bypass found in the voice path. Secret pattern scan on changed
production voice files: clean.

## 15. M78 browser results

`docs/evidence/m78/browser/M78_VOICE_BROWSER_CERT.json` — **PASS**

- 33 hard / 6 responsive / 2 accessibility / 4 security gates
- M64 shell regression retained PASS
- Real fallback operation, authenticated audio range, Play/Stop, IELTS read-aloud,
  unavailable state, responsive views, logout cleanup certified on loopback

## 16. Tests and checks (this session)

- Voice backend: 15 passed
- Frontend: 189 passed
- Voice/IELTS frontend contracts: passed
- Browser cert: PASS
- `shell=True` / public-listener scans: clean
- Secret pattern scan: clean
- `git diff --check`: clean on mission files

Full backend suite was certified under M77 (5,272 passed) and not re-run in full for
this bounded browser-hardening slice after focused regressions remained green.

## 17. Known limitations

- VoxCPM optional/uninstalled/unverified
- Nepali unverified
- Cloning disabled
- Single-host SQLite/artifact storage
- Cold native synthesis can exceed a two-second target
- Production not authorized

## 18. Production blockers

Explicit production authorization, operator hardening, privacy/retention operations,
and any approved heavy-provider installation remain required before production use.

## 19. Push/merge/deploy confirmation

No push, merge, pull request, deployment, DNS change, production database change,
credential action, paid-provider call, public listener, live trade, or Trading
Guardian change occurred.

## Explicit answers

1. **Can SaathiOS speak now?** Yes — authenticated local English speech via macOS,
   including certified browser Play on loopback.
2. **Which provider is certified?** `macos_system`
3. **Is VoxCPM installed?** No
4. **Was real VoxCPM inference executed?** No
5. **Which languages are certified?** English only
6. **Is voice cloning enabled?** No (`CAPABILITY_DISABLED`)
7. **Is production use authorized?** No

---

# Prior Completed Goal — Autonomous Mission Runtime Final Report

Status: certified. See earlier M72 sections retained below in repository history and
`docs/autonomous/M72_MISSION_RUNTIME_CERTIFICATION.md`.
