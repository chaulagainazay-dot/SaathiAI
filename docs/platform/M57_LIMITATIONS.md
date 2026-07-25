# M57 Limitations

- **Localhost-only.** Everything binds 127.0.0.1 / localhost; no public exposure,
  no 0.0.0.0, no tunnels. Not production deployment, not multi-host.
- **macOS shortcut is PREPARED, not auto-assigned.** The environment cannot safely
  enumerate all system-wide key bindings, so `⌥⌘B` is left for explicit,
  operator-verified assignment (fail-closed, to avoid overwriting an existing
  binding). The stable entry point (`scripts/macos/saathi-open.sh` →
  `saathi-local open`) is implemented and certified.
- **Login LaunchAgent is disabled by default.** Prepared and reversible
  (`com.saathi.local-launcher`); never enabled without explicit operator opt-in.
- **Pre-existing agent conflict.** A pre-existing `com.saathi.local` LaunchAgent
  may hold `*:8765`; M57 never modifies it and fails closed around it. Clean
  single-launcher daily use requires the operator to unload it.
- **Heartbeat is single-host.** 30 s interval; `node-local` health is accurate
  while the BFF runs and stale after stop — no multi-host coordination.
- **Cold-load retry** mitigates first-compile races but cannot eliminate a genuinely
  down backend; real failures still surface after retries.
- **No push, merge, deploy, production, connectors, financial/trading, or
  multi-host.** Trading Guardian remains unengaged/advisory-only.
