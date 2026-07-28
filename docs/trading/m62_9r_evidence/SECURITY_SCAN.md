# M62.9R Security & Safety Scan

Scope: `saathi/platform/paper_trading/`, `safety/`, `market_data/`, `strategy/`, `research/`,
`trading_guardian.py`, `trading_models.py`, `api.py`, plus repo-wide binding check.

## Executable-primitive scan

| Primitive | Executable occurrence in trading modules | Verdict |
|-----------|------------------------------------------|---------|
| `eval(` | none | SAFE |
| `exec(` | none | SAFE |
| `subprocess` | none | SAFE |
| `socket` | none (only docstrings: "never opens a socket") | SAFE |
| `os.system` / `__import__` | none | SAFE |
| `requests`/`httpx`/`urllib`/`websocket` | none | SAFE |

`.execute(...)` matches are SQLite parameterized statements (SQL layer), not Python `exec`.

## Prohibited-capability scan

37 files contain one or more prohibited terms (`live`, `production`, `real_money`, `margin`,
`leverage`, `short`, `option`, `future`, `perpetual`, `derivative`, `borrow`, `withdraw`,
`broker`, `credential`, `secret`, `api_key`). Every occurrence classified:

- **Rejection lists** — `trading_guardian.py` (`LEVERAGE, MARGIN, SHORT_SELLING, OPTIONS, FUTURES`),
  `paper_trading/models.py` (`LIVE, PRODUCTION, REAL_MONEY, LIVE_BROKER, LEVERAGE, MARGIN`).
- **Docstrings** — "No live broker, real money, leverage, margin, short-selling…".
- **Clamping logic** — `strategy/sizing.py`, `strategy/validation.py` (position fraction ≤ cap,
  "leverage not authorized").

No executable prohibited capability. Classification: **SAFE_CANONICAL / READ_ONLY**.

## Auto-repair scan

`execute_repair`, `apply_repair`, `repair_account`, `auto_repair`, `fix_financial_state`:
**no executable financial-repair symbol exists.** `authorize_repair_plan` marks status only and
audits `outcome="authorized_not_executed"`. The only match for `auto_repair` is
`saathi/repair/loop.py` — the unrelated auto-dev **code**-repair loop (subprocess code patching,
never pushes/deploys), classified **OUT_OF_SCOPE** for trading; it never touches financial state.

## Network-binding scan

- `scripts/start_local.sh`: `SAATHI_HOST=127.0.0.1`; UI `npm run start -- -H 127.0.0.1`.
- `saathi/server.py:5315`: `uvicorn.run(app, host=config.HOST, port=config.PORT)`.
- `saathi/config.py:92`: `HOST = os.getenv("SAATHI_HOST", "0.0.0.0")` — env fallback default is
  `0.0.0.0`; the launcher overrides to `127.0.0.1`. **Known limitation** (LEGACY_ISOLATED default);
  not a certification blocker for the bounded localhost paper-trading system, since the documented
  launch path binds loopback and no trading module opens a listener of its own.
- No `0.0.0.0` literal inside any trading module.
- No external network dependency in the trading path.

## Frontend authority

No client-side financial calculation in `saathi-os/app/trading/` or `components/trading/`
(grep for compute/reduce/price-math returned nothing outside formatting/display). The browser is a
read-only operator interface.

## Verdict

No executable prohibited behavior. No live broker, credentials, network egress, automatic repair,
Guardian/Runtime/Gateway/approval bypass, or browser financial authority. **PASS.**
