# Owner Private-Alpha Trading Acceptance Checklist

**Environment:** localhost only · paper only · no broker credentials

| # | Check | Pass / Fail / Obs | Notes |
| --- | --- | --- | --- |
| 1 | Overview shows PAPER TRADING ONLY | | |
| 2 | NO LIVE ORDERS / SIMULATED FUNDS visible | | |
| 3 | Strategy registry lists 4 catalog strategies | | |
| 4 | Strategy version immutable after activation | | |
| 5 | Regime evaluate produces deterministic labels | | |
| 6 | Policy rejection visible on bad proposal | | |
| 7 | Valid proposal shows risk sizing | | |
| 8 | LLM/strategy cannot self-approve | | |
| 9 | Human approval works | | |
| 10 | Paper order attaches via gateway path | | |
| 11 | Journal shows provenance | | |
| 12 | Backtest shows data classification | | |
| 13 | Fixture/synthetic labeled non-authoritative | | |
| 14 | Walk-forward runs | | |
| 15 | Stress lab runs | | |
| 16 | Strategy comparison honest | | |
| 17 | Kill switch blocks new paper proposals | | |
| 18 | Unreconciled blocks new proposals | | |
| 19 | No page implies real money | | |
| 20 | Refresh/restart recovery understood | | |

## Sign-off distinction

| Kind | Status in automated cert |
| --- | --- |
| Automated browser certification | May pass |
| Synthetic operator validation | Recovery suite |
| Actual owner sign-off | **Not claimed by automation** |

Owner name: ________  Date: ________  Signature: ________
