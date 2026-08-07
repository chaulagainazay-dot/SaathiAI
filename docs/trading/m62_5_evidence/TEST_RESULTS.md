# M62.5 Test & Regression Results

## New suite — `tests/test_m62_5_paper_broker.py`

**46 passed** (unit, service, persistence, gateway integration, HTTP, adversarial).

Coverage highlights:

- **Safety**: prohibited-config fail-closed (LIVE/PRODUCTION/LEVERAGE/MARGIN/SHORT/
  OPTIONS/FUTURES/PERPETUALS/DERIVATIVES/BORROWING/LIVE_BROKER), non-PAPER env rejected.
- **State machines**: broker + account transition edges; terminal immutability.
- **Fill engine (pure)**: market buy at ask+slippage; limit not-crossed → no fill;
  limit never fills above/below limit; partial fill on low liquidity; invalid quality
  / closed market block; deterministic identical `result_hash`.
- **Service flow**: reserve→fill, intent↔order separation, insufficient cash (no
  order/reservation), oversell rejected, SELL realizes P&L, partial-then-complete,
  Guardian veto before submission (intent → REJECTED, `is_trade_approval=false`).
- **Idempotency**: duplicate submission → one order; duplicate market event → one fill.
- **Cancellation**: cancel-open releases reservation; cancel-after-fill rejected;
  partial-then-cancel retains fill; fill-after-cancel rejected.
- **Halt**: blocks new orders; requires owner.
- **Persistence / restart**: order + reservation preserved; no duplicate fill after
  restart; fills immutable/append-only.
- **Tenant isolation**: cross-tenant read/cancel/account access rejected.
- **Permissions**: viewer cannot propose/submit.
- **Adversarial**: negative quantity, unsupported side (SHORT) / type (STOP),
  atomic rollback on approval failure, financial-execution tool prohibited,
  no broker import in research/strategy.
- **Gateway integration**: submit consumes approval atomically then fills through the
  Gateway; reused approval blocked; cross-tenant approval rejected; missing approval
  blocked.
- **HTTP**: full `/paper` lifecycle (create → propose → submit → process-event →
  fills → positions); unauth = 401; no order route outside `/paper`.

## Regression (all green)

| suite | result |
|---|---|
| `test_m62_4_strategy.py` + `test_m62_3_research.py` + `test_m62_2_market_data.py` + `test_m62_trading_models.py` + `test_m49_3_trading_boundary.py` | 100 passed |
| M49.1 tool_runtime (contracts/execution/idempotency/security/cancellation) | 43 passed |
| `test_m50_approval_and_runtime.py` + `test_m49_3_connector_approval_scope.py` + `test_m50_platform_identity.py` | 21 passed |
| Broad platform sweep (`-k "tool_runtime or m49 or gateway or execution or platform or m61 or approval or permission or rbac"`) | **494 passed**, 0 failed |

## Safety scan

`grep` over `saathi/platform/paper_trading/` for `requests|httpx|urllib|websocket|
socket.|api_key|secret|credential|eval(|exec(|subprocess|__import__` → only
docstring safety statements; **no executable forbidden capability**. No
live/margin/short/leverage/option/future/perpetual/derivative function definitions.
`git diff --check` clean. No public listener / deployment / production authority
changed.
