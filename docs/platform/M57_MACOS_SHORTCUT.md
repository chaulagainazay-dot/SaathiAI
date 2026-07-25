# M57 macOS Global Shortcut (Option + Command + B)

Goal: `⌥⌘B` opens `http://localhost:3000`, starting SaathiOS first if needed.

## Stable entry point
`scripts/macos/saathi-open.sh` → `saathi-local open`, which:
1. opens SaathiOS immediately if healthy;
2. otherwise starts it via the safe launcher, waits for readiness, then opens it;
3. does not require Terminal focus and does not spam duplicate tabs (a single
   launcher lock guards concurrent starts).

## Assignment status — PREPARED, not silently ACTIVE
This environment cannot safely enumerate all existing system-wide key bindings,
so the launcher **does not** assign `⌥⌘B` automatically — doing so could overwrite
an existing user shortcut. The binding is **prepared** and left for explicit,
operator-verified assignment (fail-closed).

### Operator assignment (macOS Shortcuts app)
1. Open **Shortcuts** → New Shortcut → add a **Run Shell Script** action:
   `~/SaathiAI/scripts/macos/saathi-open.sh` (or `~/.local/bin/saathi-local open`).
2. Name it "Open SaathiOS".
3. Shortcut **Details → Add Keyboard Shortcut** → press **⌥⌘B**.
4. If macOS reports the combination is already in use, choose a different key and
   record it here — **do not** overwrite an existing binding.

Mark this `MACOS_SHORTCUT_ACTIVE` only after you have assigned and verified `⌥⌘B`.
Until then it is `MACOS_SHORTCUT_PREPARED`.
