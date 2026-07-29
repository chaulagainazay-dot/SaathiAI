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
    p_wf = bt_sub.add_parser("walk-forward")
    p_wf.add_argument("--strategy", default="trend_following")
    p_wf.add_argument("--dataset", default="TRENDING")
    p_st = bt_sub.add_parser("stress")
    p_st.add_argument("--strategy", default="trend_following")
    p_sc = bt_sub.add_parser("scorecard")
    p_sc.add_argument("--strategy", default="trend_following")

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

    # M184–M191 historical data + research
    p_data = sub.add_parser("data")
    data_sub = p_data.add_subparsers(dest="action")
    p_imp = data_sub.add_parser("import")
    p_imp.add_argument("path")
    p_imp.add_argument("--adapter", default="local_file")
    p_imp.add_argument("--name", default="")
    p_imp.add_argument("--market", default="")
    p_imp.add_argument("--instrument", default="UNKNOWN")
    p_imp.add_argument("--calendar", default="DEFAULT_24_5")
    p_imp.add_argument("--currency", default="USD")
    data_sub.add_parser("list")
    p_insp = data_sub.add_parser("inspect")
    p_insp.add_argument("dataset_id")
    p_insp.add_argument("--version", default="")
    p_q = data_sub.add_parser("quarantine")
    p_q.add_argument("dataset_id")
    p_q.add_argument("version")
    p_q.add_argument("--reason", default="operator_quarantine")
    data_sub.add_parser("validate")  # alias list quality via inspect latest

    p_cal = sub.add_parser("calendar")
    cal_sub = p_cal.add_subparsers(dest="action")
    cal_sub.add_parser("inspect")

    p_res = sub.add_parser("research")
    res_sub = p_res.add_subparsers(dest="action")
    p_rr = res_sub.add_parser("run")
    p_rr.add_argument("--strategy", default="trend_following")
    p_rr.add_argument("--dataset-id", default="")
    p_rr.add_argument("--period", default="FULL")
    p_rr.add_argument("--seed", type=int, default=42)
    p_rs = res_sub.add_parser("status")
    p_rs.add_argument("--run-id", default="")
    p_rmc = res_sub.add_parser("monte-carlo")
    p_rmc.add_argument("--strategy", default="trend_following")
    p_rmc.add_argument("--dataset-id", default="")
    p_rmc.add_argument("--n", type=int, default=100)

    p_sq = sub.add_parser("strategy-qualify")
    p_sq.add_argument("--strategy", default="trend_following")
    p_sq.add_argument("--dataset-id", default="")

    p_sc2 = sub.add_parser("strategy-scorecard")
    p_sc2.add_argument("--strategy", default="trend_following")
    p_sc2.add_argument("--dataset-id", default="")

    # M192–M199 paper activation governance
    p_pg = sub.add_parser("paper-gov")
    pg_sub = p_pg.add_subparsers(dest="action")
    pg_sub.add_parser("status")
    p_pc = pg_sub.add_parser("create")
    p_pc.add_argument("--name", default="Paper Fund")
    p_pc.add_argument("--cash", default="100000")
    p_pp = pg_sub.add_parser("portfolio")
    p_pp.add_argument("portfolio_id")
    pg_sub.add_parser("portfolios")
    p_pa = pg_sub.add_parser("approve")
    p_pa.add_argument("approval_id")
    p_pa.add_argument("--actor", default="operator:cli")
    p_pa.add_argument("--notes", default="")
    p_pa.add_argument("--reason", default="")
    p_prj = pg_sub.add_parser("reject")
    p_prj.add_argument("approval_id")
    p_prj.add_argument("--actor", default="operator:cli")
    p_prj.add_argument("--notes", default="")
    p_prj.add_argument("--reason", default="rejected")
    p_pact = pg_sub.add_parser("activate")
    p_pact.add_argument("--strategy", required=True)
    p_pact.add_argument("--approval-id", required=True)
    p_pact.add_argument("--portfolio-id", default="")
    p_pact.add_argument("--actor", default="operator:cli")
    p_po = pg_sub.add_parser("orders")
    p_po.add_argument("portfolio_id")
    p_pos = pg_sub.add_parser("positions")
    p_pos.add_argument("portfolio_id")
    p_pan = pg_sub.add_parser("analytics")
    p_pan.add_argument("portfolio_id")
    p_prec = pg_sub.add_parser("reconcile")
    p_prec.add_argument("portfolio_id")
    p_pst = pg_sub.add_parser("stop")
    p_pst.add_argument("--strategy", required=True)
    p_pst.add_argument("--reason", default="operator stop")
    p_pk = pg_sub.add_parser("kill")
    p_pk.add_argument("--reason", default="cli kill")
    p_pk.add_argument("--actor", default="operator:cli")
    # M200–M207
    pg_sub.add_parser("storage-status")
    pg_sub.add_parser("migrate")
    p_cc = pg_sub.add_parser("campaign-create")
    p_cc.add_argument("--strategy", default="trend_following")
    p_cs = pg_sub.add_parser("campaign-start")
    p_cs.add_argument("campaign_id")
    p_cs.add_argument("--actor", default="operator:cli")
    p_ccomp = pg_sub.add_parser("campaign-complete")
    p_ccomp.add_argument("campaign_id")
    p_ccomp.add_argument("--actor", default="operator:cli")
    p_ev = pg_sub.add_parser("events")
    p_ev.add_argument("--limit", type=int, default=50)
    p_bc = pg_sub.add_parser("backup-create")
    p_bc.add_argument("--dest", default="")
    p_bv = pg_sub.add_parser("backup-verify")
    p_bv.add_argument("path")
    p_rt = pg_sub.add_parser("recovery-test")
    p_rt.add_argument("source")
    p_rt.add_argument("--dest", default="")
    pg_sub.add_parser("report-daily")
    pg_sub.add_parser("report-weekly")
    pg_sub.add_parser("incidents")
    pg_sub.add_parser("worker-status")
    p_rp = pg_sub.add_parser("replay")
    p_rp.add_argument("portfolio_id")
    p_sn = pg_sub.add_parser("snapshot")
    p_sn.add_argument("portfolio_id")

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
        if args.action == "walk-forward":
            return _out(svc.run_walk_forward(strategy_slug=args.strategy, dataset=args.dataset))
        if args.action == "stress":
            return _out(svc.run_stress(strategy_slug=args.strategy))
        if args.action == "scorecard":
            return _out(svc.research_scorecard(strategy_slug=args.strategy))
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

    if args.cmd == "data":
        if args.action == "import":
            return _out(svc.import_historical_dataset(
                args.path,
                adapter=args.adapter,
                dataset_name=args.name or "",
                market=args.market,
                default_instrument=args.instrument,
                calendar_name=args.calendar,
                currency=args.currency,
            ))
        if args.action == "list":
            return _out(svc.list_historical_datasets())
        if args.action == "inspect":
            return _out(svc.inspect_historical_dataset(
                args.dataset_id, version=args.version or None,
            ))
        if args.action == "quarantine":
            return _out(svc.quarantine_historical_dataset(
                args.dataset_id, args.version, reason=args.reason,
            ))
        if args.action == "validate":
            return _out(svc.list_historical_datasets())
        return 2

    if args.cmd == "calendar":
        if args.action == "inspect":
            return _out(svc.historical_calendars())
        return 2

    if args.cmd == "research":
        if args.action == "run":
            return _out(svc.run_historical_research(
                strategy_slug=args.strategy,
                dataset_id=args.dataset_id,
                period=args.period,
                seed=args.seed,
            ))
        if args.action == "status":
            return _out(svc.historical_research_status(args.run_id or None))
        if args.action == "monte-carlo":
            return _out(svc.run_monte_carlo_analysis(
                strategy_slug=args.strategy,
                dataset_id=args.dataset_id,
                n_simulations=args.n,
            ))
        return 2

    if args.cmd == "strategy-qualify":
        return _out(svc.qualify_strategy_historical(
            args.strategy, dataset_id=args.dataset_id,
        ))

    if args.cmd == "strategy-scorecard":
        if args.dataset_id:
            return _out(svc.qualify_strategy_historical(
                args.strategy, dataset_id=args.dataset_id,
            ))
        return _out(svc.research_scorecard(strategy_slug=args.strategy))

    if args.cmd == "paper-gov":
        from saathi.platform.tg.paper_activation.service import default_paper_gov, PaperGovError
        gov = default_paper_gov()
        if args.action == "status":
            return _out(gov.status())
        if args.action == "create":
            return _out(gov.create_portfolio(name=args.name, starting_cash=args.cash))
        if args.action == "portfolio":
            return _out(gov.get_portfolio(args.portfolio_id))
        if args.action == "portfolios":
            return _out(gov.list_portfolios())
        if args.action == "approve":
            return _out(gov.decide_approval(
                approval_id=args.approval_id, decision="approve",
                operator_id=args.actor, operator_identity=args.actor,
                notes=args.notes, reason=args.reason or "cli approve",
            ))
        if args.action == "reject":
            return _out(gov.decide_approval(
                approval_id=args.approval_id, decision="reject",
                operator_id=args.actor, operator_identity=args.actor,
                notes=args.notes, reason=args.reason or "cli reject",
            ))
        if args.action == "activate":
            try:
                return _out(gov.activate_strategy(
                    strategy_slug=args.strategy,
                    approval_id=args.approval_id,
                    portfolio_id=args.portfolio_id or None,
                    operator_identity=args.actor,
                ))
            except PaperGovError as e:
                return _out({"error": e.code, "message": e.message})
        if args.action == "orders":
            return _out(gov.list_orders(args.portfolio_id))
        if args.action == "positions":
            return _out(gov.list_positions(args.portfolio_id))
        if args.action == "analytics":
            return _out(gov.analytics(args.portfolio_id))
        if args.action == "reconcile":
            return _out(gov.reconcile(args.portfolio_id))
        if args.action == "stop":
            return _out(gov.halt_strategy(args.strategy, reason=args.reason or "cli stop"))
        if args.action == "kill":
            try:
                return _out(gov.activate_kill_switch(
                    scope=KillSwitchScope.GLOBAL, reason=args.reason or "cli kill",
                    activated_by=args.actor, source_identity="operator",
                ))
            except TypeError:
                return _out(gov.activate_kill_switch(
                    reason=args.reason or "cli kill", activated_by=args.actor,
                ))
        # M200–M207 durable extensions
        if args.action == "storage-status":
            from saathi.platform.tg.paper_activation.durable.service import default_durable_gov
            return _out(default_durable_gov().storage_status())
        if args.action == "migrate":
            from saathi.platform.tg.paper_activation.durable.service import default_durable_gov
            return _out(default_durable_gov().migrate())
        if args.action == "campaign-create":
            from saathi.platform.tg.paper_activation.durable.service import default_durable_gov
            return _out(default_durable_gov().campaign_create(strategy_slug=args.strategy))
        if args.action == "campaign-start":
            from saathi.platform.tg.paper_activation.durable.service import default_durable_gov
            return _out(default_durable_gov().campaign_start(args.campaign_id, operator_identity=args.actor))
        if args.action == "campaign-complete":
            from saathi.platform.tg.paper_activation.durable.service import default_durable_gov
            return _out(default_durable_gov().campaign_complete(args.campaign_id, operator_identity=args.actor))
        if args.action == "events":
            from saathi.platform.tg.paper_activation.durable.service import default_durable_gov
            return _out(default_durable_gov().list_events(limit=args.limit))
        if args.action == "backup-create":
            from saathi.platform.tg.paper_activation.durable.service import default_durable_gov
            return _out(default_durable_gov().backup_create(args.dest or "data/platform/paper_backups"))
        if args.action == "backup-verify":
            from saathi.platform.tg.paper_activation.durable.service import default_durable_gov
            return _out(default_durable_gov().backup_verify(args.path))
        if args.action == "recovery-test":
            from saathi.platform.tg.paper_activation.durable.service import default_durable_gov
            return _out(default_durable_gov().recovery_test(args.source, args.dest or "data/platform/paper_recovery.db"))
        if args.action == "report-daily":
            from saathi.platform.tg.paper_activation.durable.service import default_durable_gov
            return _out(default_durable_gov().report_daily())
        if args.action == "report-weekly":
            from saathi.platform.tg.paper_activation.durable.service import default_durable_gov
            return _out(default_durable_gov().report_weekly())
        if args.action == "incidents":
            from saathi.platform.tg.paper_activation.durable.service import default_durable_gov
            return _out(default_durable_gov().list_incidents())
        if args.action == "worker-status":
            from saathi.platform.tg.paper_activation.durable.service import default_durable_gov
            g = default_durable_gov()
            return _out({"worker_id": g.worker_id, "claim": g.process_queue_once(), "paper_only": True})
        if args.action == "replay":
            from saathi.platform.tg.paper_activation.durable.service import default_durable_gov
            return _out(default_durable_gov().replay(args.portfolio_id))
        if args.action == "snapshot":
            from saathi.platform.tg.paper_activation.durable.service import default_durable_gov
            return _out(default_durable_gov().snapshot(args.portfolio_id))
        return 2

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
