# M17.24 Architecture — All Browser Dispatch Governed

## Position

Extends M17.23: every production-reachable browser side effect enters the
**same** ExecutionGateway family (`browser`), with attribution and fail-closed
legacy paths. No second browser engine.

```text
Caller (API / agent tool / connector / Control Center / scheduler context)
  → require_governed_context (actor, mission/run when required, approval, schedule, trigger, trading)
  → GovernedBrowser.execute
  → domain / risk / prohibited policy
  → ToolIntent (family=browser)
  → ExecutionGateway.submit
  → BrowserAdapter
       ├─ fake (tests)
       └─ BrowserService._open_direct (tiers only after authorization)
  → Evidence / security timeline / run ledger / metrics
```

## Allowed low-level adapter locations

See `saathi/browser/guard.py` `LOW_LEVEL_DRIVER_ALLOWLIST`.

Includes: browser tiers + governed adapter, computer_agent CDP driver (via
ComputerAdapter), human_browser Mac agent stack, fail-closed tool wrappers.

## Prohibited patterns

- Product modules importing `playwright` / `selenium` / `LiveBrowserDriver` outside allowlist
- `BrowserService.open(governed=False)` on production singleton
- Raw `agent-browser` CLI / AppleScript browser control without `SAATHI_ALLOW_RAW_BROWSER=1`
- Using generic browser approval as trading authorization
- Scheduler / event trigger dispatch without trusted context flags

## Trading Guardian

Browser gateway **defers** to Trading Guardian for trading-classified actions
and does not engage the finance trade stack for ordinary browse/read work.
