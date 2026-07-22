# M17.23 Architecture — Governed Browser via ExecutionGateway

## Position

Browser actions are a **family** on the universal ExecutionGateway (M17.22),
not a second engine.

```text
Caller
  → GovernedBrowser.execute
  → domain policy (policy.py)
  → ToolIntent (capability=browser)
  → ExecutionGateway.submit
  → BrowserAdapter.dispatch
       ├─ fake mode (tests)
       └─ BrowserService tiers (HTTP / Playwright / Camofox)
  → Evidence / Security / Ledger / metrics
```

## Modules

| Module | Role |
|--------|------|
| `saathi/browser/policy.py` | Domain, risk, injection, path safety |
| `saathi/browser/governed.py` | ToolIntent builder, adapter, GovernedBrowser |
| `saathi/browser/service.py` | Existing tiers; optional `governed=True` |

## Non-goals

New browser engine, new approval system, banking/trading automation,
CAPTCHA/MFA bypass, unrestricted JS eval, Trading Guardian engagement.
