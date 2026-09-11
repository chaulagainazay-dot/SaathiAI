# TEST-INFRA-1 — Final Certification

## Verdict

**`TEST_INFRA_1_OFFLINE_SUITE_CERTIFIED`**

## Certification bar

| Requirement | Status | Evidence |
|---|---|---|
| Hang root cause identified | **MET** | `TEST_HANG_DB_LOCK`, with a faulthandler stack showing both threads blocked in `SecurityStore.__init__` schema DDL — `ROOT_CAUSE.md` |
| Problematic test/fixture isolated | **MET** | reduced from 387 files to a two-test pair — `SUITE_PARTITION_LOG.md` |
| Deterministic fix or correct marker isolation | **MET — fixed, not masked** | leaked-connection fix + security-store isolation; the hanging test keeps its unbounded join and now runs in 0.02 s |
| Canonical offline suite defined | **MET** | `OFFLINE_SUITE_CONTRACT.md` |
| Offline suite completes with a pytest summary | **MET** | `7630 passed, 2 skipped, 12 deselected in 668.23s` |
| No network dependency in offline suite | **MET** | zero sockets during the stall; loopback/mocked/negative-test hosts only — `NETWORK_TEST_INVENTORY.md` |
| T-NEXT-4 / T-NEXT-4.1 regressions still pass | **MET** | 82 + 15 + 340 passed, zero regression |
| No trading authority change | **MET** | see below |

## Authority audit

No trading authority was touched. Verified by diff — the four changed production
files are `saathi/security/store.py`, `saathi/providers/insforge/{migration,provider}.py`,
and `saathi/mcp_governance/events.py`. None is in the trading plane.

| Authority | Status |
|---|---|
| ExecutionGateway | **unchanged** |
| Trading Guardian | **unchanged** |
| PortfolioRiskEngine | **unchanged** |
| PortfolioConstructionEngine | **unchanged** |
| Approval | **unchanged** |
| Canonical Fund Ledger | **unchanged** |

```
NO_LIVE_TRADING
NO_REAL_BROKER
NO_WITHDRAWAL
NO_LEVERAGE
NO_LLM_EXECUTION_AUTHORITY
NO_TRADINGAGENTS_RUNTIME_DEPENDENCY
```

## Security audit

- No broker connectivity introduced.
- No new network egress in the certification suite — the change to
  `test_m18_4_insforge_migration.py` **removes** four loopback connection attempts
  by injecting `httpx.MockTransport`.
- No credentials, keys, or `.env` added.
- Net security improvement: the test suite no longer writes to the operator's
  real `~/.saathi/security.db`.

## Shadow-execution readiness

**Unchanged by this mission** — still gated on the T-NEXT-4.1 prerequisites, none
of which this mission addressed. What did change is that a full-suite regression
can now actually be run to completion before any such step, which was not
previously possible.

## TA-1 readiness

**Unblocked from the test-infrastructure side.** TA-1 touches `market_data`,
`provider_descriptor`, and `research_orchestrator/sessions`; it needs a
trustworthy regression baseline, and there now is one. The ordering constraint
from the T-NEXT-4 evaluation still stands and is a product decision, not a
testing one.

## Next recommended mission

**TEST-INFRA-2 — CI wiring and suite economics.** Wire the canonical offline
command into CI, then address the 11-minute serial runtime: audit shared-path
defaults so `pytest-xdist` is safe, and look at the fifteen tests over 7 s. The
`SecurityStore` defect suggests other stores may share the same
real-home-directory pattern — worth a sweep before parallelising anything.
