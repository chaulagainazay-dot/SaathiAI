# Worktree Reconciliation — 2026-09

This record classifies the pre-existing dirty state found before the final
canonical runtime freeze. No reset, stash, blanket clean, or database change
was performed.

| Path | Classification | Origin | Decision | Reason | Validation |
| --- | --- | --- | --- | --- | --- |
| `.claude/settings.json` | LOCAL_MACHINE_CONFIGURATION | Local Claude configuration; newline-only diff | KEEP_LOCAL_IGNORE | No product behavior; preserve operator configuration | Diff is newline-only |
| `saathi-os/README.md` | VALUABLE_UNCOMMITTED_WORK | SaathiOS product identity correction | KEEP_AND_COMMIT | User-facing documentation must say SaathiOS | Frontend suite/build passed |
| `saathi-os/app/layout.jsx` | VALUABLE_UNCOMMITTED_WORK | SaathiOS product metadata correction | KEEP_AND_COMMIT | Browser title and metadata are product-facing | Frontend suite/build passed |
| `saathi-os/app/os/page.jsx` | VALUABLE_UNCOMMITTED_WORK | Canonical microphone-surface consolidation | KEEP_AND_COMMIT | Removes duplicate legacy push-to-talk surface | Voice-surface regression passed |
| `saathi-os/components/Shell.jsx` | VALUABLE_UNCOMMITTED_WORK | Canonical microphone-surface consolidation | KEEP_AND_COMMIT | Keeps runtime dock off dedicated capture routes | Voice-surface regression passed |
| `saathi-os/components/chat/ChatWorkspace.jsx` | VALUABLE_UNCOMMITTED_WORK | Canonical microphone-surface consolidation | KEEP_AND_COMMIT | Removes competing chat VoiceControl | Frontend suite passed |
| `saathi-os/components/mobile/MobileSaathi.jsx` | VALUABLE_UNCOMMITTED_WORK | Canonical microphone-surface consolidation | KEEP_AND_COMMIT | Removes competing mobile microphone | Frontend suite passed |
| `saathi-os/lib/voice-surface.test.js` | VALUABLE_UNCOMMITTED_WORK | Regression coverage for canonical voice ownership | KEEP_AND_COMMIT | Prevents legacy surface reintroduction | Included in 591-test suite |
| `.specify/` integration, scripts, templates, manifests | VALUABLE_UNCOMMITTED_WORK | Native Spec Kit governance integration | KEEP_AND_COMMIT | Referenced by Brain.md and project delivery workflow | Static review; no secrets found |
| `docs/design/nepse-ti/` | GENERATED_ARTIFACT | Design/canvas export, including bundled HTML | DEFER | Valuable design evidence, but generated and large; not runtime source | Retained unchanged; no credentials detected |

## Safety decisions

- No repositories, worktrees, databases, credentials, or runtime state were
  deleted or moved.
- `node_modules`, `.next`, virtual environments, `.env` files, caches, logs,
  and model artifacts were not added.
- The SaathiOS application symlink remains the single canonical boundary.
- The design export remains recoverable and intentionally uncommitted pending a
  separate artifact-storage decision.
