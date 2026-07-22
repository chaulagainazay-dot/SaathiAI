# M17.26 Architecture — Production Browser Adapters & Evidence

## Flow

```text
Caller / Workflow step
  → InteractiveBrowser.open_session / act / handoff / resume / close
  → BrowserSessionStore (ownership, lease, status, ledger)
  → DomainPolicyService (environment-aware, fail-closed)
  → Action taxonomy + approval + Trading Guardian gate
  → EvidenceRedactionPipeline (classify → mask/suppress → metadata)
  → GovernedBrowser.execute → ExecutionGateway
  → BrowserAdapter (fake or service)
       ↳ ProductionBrowserAdapter.act (session-bound sandbox/CDP)
       ↳ HumanMacAdapter (same contract + human takeover)
  → Adapter health / reconnect / reconcile
  → BrowserAdapterMonitor → Control Center snapshot
```

## Canonical adapter contract

`BrowserSessionAdapter` (`adapter_contract.py`):

| Method | Role |
|--------|------|
| `attach_session` | Bind endpoint/sandbox to `session_id` |
| `validate_session` | Ownership / lease / mission |
| `health` | AdapterHealthState + capabilities |
| `navigate` / `inspect` / `act` | Execute **validated** GovernedActionRequest |
| `capture_evidence` | Metadata only — redaction upstream |
| `pause` / `resume` | Bounded control |
| `reconcile` | Resolve uncertain without re-execution |
| `close_session` | Detach; do not kill unrelated browsers |

Adapters **must not** decide authorization, policy, approval, Trading Guardian,
domain allow, or retry. They fail closed if context is missing.

## Production CDP / sandbox adapter

`ProductionBrowserAdapter`:

* Default `allow_live=False` (sandbox) for tests — never connects to the user's real profile.
* Live attach only to explicit loopback CDP endpoints when `allow_live=True`.
* Tracks scoped pages per session; unrelated tabs denied.
* Health states: UNKNOWN → STARTING → HEALTHY / DEGRADED / DISCONNECTED /
  RECONNECTING / RECONCILIATION_REQUIRED / UNAVAILABLE / CLOSED.
* DEGRADED blocks high-risk action classes.
* Disconnect after action marks reconciliation; reconnect revalidates ownership,
  page identity, domain, kill switch, approval; bounded reconnect attempts.
* External-effect actions never blind-retry after uncertain outcome.
* Raw page objects never exposed (`expose_raw_page` always denied).

## Human Mac adapter

`HumanMacAdapter` wraps `ProductionBrowserAdapter`:

* Modes: automated_governed, human_takeover, human_completion, human_decline, adapter_disconnect.
* Takeover pauses agent control; concurrent agent actions denied.
* Bounded to browser app — app switch requires separate permission.
* Sensitive manual input never logged.
* Human completion does **not** count as approval.
* Raw `osascript` blocked at product boundary.

## Domain policy

See `docs/M17_26_DOMAIN_POLICY.md`. Production: deny-by-default, HTTPS-only,
no localhost/private/file/javascript/data, no wildcards, redirect/popup revalidation.

## Evidence

See `docs/M17_26_EVIDENCE_REDACTION.md`. Classification drives redaction mode;
highest-risk rule wins; OCR is optional secondary only.

## Workflow migration

`workflow_migrate.parse_workflow_step` + `execute_workflow_step` require governed
fields, reject script/eval/raw bypass fields, map CAPTCHA/MFA to handoff, and
call `InteractiveBrowser.act`.

## Modules

| Module | Role |
|--------|------|
| `domain_policy.py` | Env-aware domain policy + normalization |
| `adapter_contract.py` | Interface, health, typed errors |
| `production_adapter.py` | CDP/sandbox production adapter |
| `human_mac_adapter.py` | Human Mac governed adapter |
| `evidence_redaction.py` | Classification + redaction pipeline |
| `workflow_migrate.py` | Workflow step schema + IB.act migration |
| `adapter_monitor.py` | Alerts + Control Center snapshot |
| `interactive.py` | Wires adapter attach, domain env, evidence |
| `governed.py` | Service interactive → production adapter |
| `guard.py` | Allowlist + AST + production config checks |
| `policy.py` | Delegates to DomainPolicyService when env/production |

## Trading Guardian

Financial browser actions still require `trading_authorized=True` (TG). Generic
browser approval, domain allowlist, and form-submit approval do not authorize
trades. No live trading capability added. Trading screenshots → `TRADING_SENSITIVE`.

## Production configuration guards

`validate_production_browser_config` / `production_config_violations` block:

* RAW browser env in production
* Empty domain allowlist when browser enabled
* Wildcards, file://, private networks, unrestricted custom protocols
* Screenshots without redaction policy
* Traces without retention/redaction
* Unrestricted desktop control
