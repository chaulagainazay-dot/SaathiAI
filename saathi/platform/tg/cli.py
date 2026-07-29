"""M174 — Trading Guardian CLI.

    python -m saathi.platform.tg.cli strategy list
    python -m saathi.platform.tg.cli strategy inspect <slug>
    python -m saathi.platform.tg.cli regime evaluate
    python -m saathi.platform.tg.cli backtest run [--strategy slug]
    python -m saathi.platform.tg.cli backtest compare
    python -m saathi.platform.tg.cli proposal create --strategy slug
    python -m saathi.platform.tg.cli proposal review <id> --decision approve|reject
    python -m saathi.platform.tg.cli paper portfolio
    python -m saathi.platform.tg.cli paper reconcile
    python -m saathi.platform.tg.cli journal export
    python -m saathi.platform.tg.cli kill-switch activate --reason "..."
    python -m saathi.platform.tg.cli kill-switch status
    python -m saathi.platform.tg.cli posture

Paper only. No live orders. No broker credentials.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from saathi.platform.tg.service import default_tg_service, TradingGuardianService
from saathi.platform.tg.fixtures import trending_snapshot, mean_reverting_snapshot, momentum_snapshot
from saathi.platform.tg.domain import KillSwitchScope
from saathi.platform.tg.strategies import list_catalog


def _out(data: Any) -> int:
    print(json.dumps(data, indent=2, default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="saathi-trading", description="Trading Guardian CLI (paper only)")
    sub = parser.add_subparsers(dest="cmd")

    # strategy
    p_strat = sub.add_parser("strategy")
    strat_sub = p_strat.add_subparsers(dest="action")
    strat_sub.add_parser("list")
    p_insp = strat_sub.add_parser("inspect")
    p_insp.add_argument("slug")

    # regime
    p_reg = sub.add_parser("regime")
    reg_sub = p_reg.add_subparsers(dest="action")
    p_re = reg_sub.add_parser("evaluate")
    p_re.add_argument("--fixture", default="trending", choices=["trending", "mean_reverting", "momentum"])

    # backtest
    p_bt = sub.add_parser("backtest")
    bt_sub = p_bt.add_subparsers(dest="action")
    p_run = bt_sub.add_parser("run")
    p_run.add_argument("--strategy", default="trend_following")
    p_run.add_argument("--dataset", default="TRENDING")
    p_run.add_argument("--n", type=int, default=40)
    bt_sub.add_parser("compare")

    # proposal
    p_prop = sub.add_parser("proposal")
    prop_sub = p_prop.add_subparsers(dest="action")
    p_pc = prop_sub.add_parser("create")
    p_pc.add_argument("--strategy", default="trend_following")
    p_pc.add_argument("--fixture", default="trending", choices=["trending", "mean_reverting", "momentum"])
    p_pr = prop_sub.add_parser("review")
    p_pr.add_argument("proposal_id")
    p_pr.add_argument("--decision", required=True, choices=["approve", "reject"])
    p_pr.add_argument("--actor", default="operator:cli")

    # paper
    p_paper = sub.add_parser("paper")
    paper_sub = p_paper.add_subparsers(dest="action")
    paper_sub.add_parser("portfolio")
    paper_sub.add_parser("reconcile")

    # journal
    p_j = sub.add_parser("journal")
    j_sub = p_j.add_subparsers(dest="action")
    j_sub.add_parser("export")

    # kill-switch
    p_ks = sub.add_parser("kill-switch")
    ks_sub = p_ks.add_subparsers(dest="action")
    p_ksa = ks_sub.add_parser("activate")
    p_ksa.add_argument("--reason", required=True)
    p_ksa.add_argument("--scope", default="GLOBAL")
    p_ksa.add_argument("--actor", default="operator:cli")
    ks_sub.add_parser("status")

    sub.add_parser("posture")

    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 2

    svc: TradingGuardianService = default_tg_service()
    svc.seed_catalog()

    if args.cmd == "posture":
        return _out(svc.posture())

    if args.cmd == "strategy":
        if args.action == "list":
            return _out({
                "catalog": list_catalog(),
                "registered": [s.to_public() for s in svc.registry.list()],
                "paper_only": True,
            })
        if args.action == "inspect":
            s = svc.registry.get_by_slug(args.slug, org_id="local", workspace_id="local")
            if not s:
                # fall back to catalog
                from saathi.platform.tg.strategies import get_catalog_strategy
                try:
                    return _out(get_catalog_strategy(args.slug).spec().to_public())
                except KeyError:
                    print(json.dumps({"error": "not found"}), file=sys.stderr)
                    return 1
            return _out(s.to_public())
        return 2

    if args.cmd == "regime":
        if args.action == "evaluate":
            snap = {
                "trending": trending_snapshot,
                "mean_reverting": mean_reverting_snapshot,
                "momentum": momentum_snapshot,
            }[args.fixture]()
            return _out(svc.evaluate_regime(snap))
        return 2

    if args.cmd == "backtest":
        if args.action == "run":
            return _out(svc.run_backtest(strategy_slug=args.strategy, dataset=args.dataset, n=args.n))
        if args.action == "compare":
            return _out(svc.compare_strategies())
        return 2

    if args.cmd == "proposal":
        if args.action == "create":
            snap = {
                "trending": trending_snapshot,
                "mean_reverting": mean_reverting_snapshot,
                "momentum": momentum_snapshot,
            }[args.fixture]()
            return _out(svc.generate_proposal(strategy_slug=args.strategy, snapshot=snap))
        if args.action == "review":
            return _out(svc.review_proposal(
                args.proposal_id, decision=args.decision, actor=args.actor,
            ))
        return 2

    if args.cmd == "paper":
        if args.action == "portfolio":
            return _out({
                "cash": "100000",
                "equity": "100000",
                "funds_label": "SIMULATED",
                "paper_only": True,
                "live_money": False,
                "disclaimer": "SIMULATED FUNDS — NOT REAL MONEY",
                "note": "Canonical durable paper portfolios live in M62 paper_trading service.",
            })
        if args.action == "reconcile":
            return _out({
                "status": "OK",
                "paper_only": True,
                "note": "Reconciliation is owned by saathi.platform.paper_trading.reconciliation",
            })
        return 2

    if args.cmd == "journal":
        if args.action == "export":
            print(svc.journal.export())
            return 0
        return 2

    if args.cmd == "kill-switch":
        if args.action == "activate":
            return _out(svc.activate_kill_switch(
                scope=KillSwitchScope(args.scope),
                reason=args.reason,
                activated_by=args.actor,
                source_identity="operator",
            ))
        if args.action == "status":
            return _out({"kill_switches": svc.kill_switch_status(), "paper_only": True})
        return 2

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
