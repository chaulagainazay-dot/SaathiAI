# M49.4 Residual Risks

| ID | Risk | Severity | Mitigation / acceptance |
|---|---|---|---|
| R1 | 59 LEGACY_BOUNDED executable handlers | Medium | Governance gate; migrate in M50+ |
| R2 | Agent persona still mentions run_shell | Low | Runtime PROHIBITED |
| R3 | Single-host idempotency only | Medium | Document MULTI_HOST_UNSAFE |
| R4 | Live connectors uncertified | Medium | Dry-run only; do not enable |
| R5 | Stacked draft PRs unmerged | Process | Owner-gated merge sequence |
| R6 | computer_agent / connectors.platform parallel registries | Medium | Not M49 execution path; keep discovery-only |
| R7 | chatgpt_browser applescript helper exists in tools | Medium | Deferred browser; not freeform shell path of execute_tool |

Residual risk count: **7** accepted, **0** critical unmitigated on gateway path.
