# Trading Guardian Operator Runbook (Paper Only)

## Safety frame

Always assume:

- **PAPER TRADING ONLY**
- **NO LIVE ORDERS**
- **SIMULATED FUNDS**
- Historical performance is not future performance
- Human approval does not remove financial risk

## Daily checks

1. `python -m saathi.platform.tg.cli posture` — confirm ADVISORY / paper-only.
2. `python -m saathi.platform.tg.cli kill-switch status`
3. Open `/trading` and `/trading/policy` — verify banners and kill-switch state.
4. Review `/trading/journal` for unexpected entries.

## Generate and review a proposal

```bash
python -m saathi.platform.tg.cli proposal create --strategy trend_following --fixture trending
python -m saathi.platform.tg.cli proposal review <proposal_id> --decision approve --actor operator:you
```

Paper submission still requires ExecutionGateway paper tools (M62 path). TG does not place orders directly.

## Backtest / compare

```bash
python -m saathi.platform.tg.cli backtest run --strategy kotegawa_mean_reversion
python -m saathi.platform.tg.cli backtest compare
```

## Emergency kill switch

```bash
python -m saathi.platform.tg.cli kill-switch activate --reason "operator halt" --actor operator:you
```

Or UI: `/trading/policy` → Activate global kill switch.

Kill switches cannot be cleared by strategies, agents, or LLMs.

## Incident notes

- If policy unexpectedly allows a proposal: export journal, trip kill switch, suspend strategy.
- If simulated P&L is misread as real: reinforce SIMULATED FUNDS labeling; no real money is held.
