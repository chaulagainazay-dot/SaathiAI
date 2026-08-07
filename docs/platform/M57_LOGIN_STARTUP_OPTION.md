# M57 Optional Login Startup (LaunchAgent)

Prepared but **disabled by default**. Starts SaathiOS at user login via a
localhost-only LaunchAgent. Reversible, no sudo, no secrets embedded, bounded logs.

## Distinct label (no clobber)
Label `com.saathi.local-launcher` — intentionally distinct from any pre-existing
`com.saathi.local` agent, which is never modified.

## Commands
```bash
saathi-local install-login     # writes ~/Library/LaunchAgents/com.saathi.local-launcher.plist (DISABLED)
launchctl load  ~/Library/LaunchAgents/com.saathi.local-launcher.plist   # explicit opt-in to enable
launchctl unload ~/Library/LaunchAgents/com.saathi.local-launcher.plist  # disable
saathi-local uninstall-login   # unload + remove the plist
```

It runs `saathi-local start` (localhost-only) and logs to `~/.saathi/logs`. It is
**not** activated during M57 and must never be enabled without explicit operator
instruction.
