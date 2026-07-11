# M15.2 — Agent Security Red-Team Harness (Spec)
Constitution v1.0. Build a SaathiOS-owned, isolated, deterministic adversarial
security harness proving M8–M15.1 boundaries hold under attack. Deterministic
probes are authoritative; HackAgent (optional, pinned, local-only, cloud-sync
off) is advisory and environment-blocked when absent. Never on the production
path. Targets are in-process/loopback only; production URLs blocked.
## Requirements
See traceability.json (M15-2-PI/JB/GOAL/TOOL/APPROVAL/MEM/PRIV/MCP/WEBHOOK/VOICE/
SECRET/REGRESSION). Each maps to a probe + a passing deterministic test.
