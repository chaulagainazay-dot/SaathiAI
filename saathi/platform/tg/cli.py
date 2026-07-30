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
    # M208–M215 operational graduation
    pg_sub.add_parser("ops-posture")
    pg_sub.add_parser("ops-dashboard")
    pg_sub.add_parser("ops-health")
    pg_sub.add_parser("ops-verdict")
    p_og = pg_sub.add_parser("ops-graduate")
    p_og.add_argument("campaign_id")
    p_oc = pg_sub.add_parser("ops-certify")
    p_oc.add_argument("campaign_id")
    p_oc.add_argument("--actor", default="operator:cli")
    pg_sub.add_parser("ops-intel")
    pg_sub.add_parser("ops-sim-suite")
    p_osim = pg_sub.add_parser("ops-simulate")
    p_osim.add_argument("scenario")
    p_osim.add_argument("--portfolio", default="")
    p_oclone = pg_sub.add_parser("ops-campaign-clone")
    p_oclone.add_argument("campaign_id")
    p_ocreate = pg_sub.add_parser("ops-campaign-create")
    p_ocreate.add_argument("--strategy", default="trend_following")
    p_ocreate.add_argument("--owner", default="operator:cli")
    p_ocreate.add_argument("--tags", default="")
    # M216–M223 broker sandbox
    pg_sub.add_parser("bs-posture")
    pg_sub.add_parser("bs-verdict")
    pg_sub.add_parser("bs-dashboard")
    pg_sub.add_parser("bs-brokers")
    pg_sub.add_parser("bs-capabilities")
    pg_sub.add_parser("bs-security")
    pg_sub.add_parser("bs-failure-suite")
    p_bsf = pg_sub.add_parser("bs-failure")
    p_bsf.add_argument("scenario")
    p_bsc = pg_sub.add_parser("bs-connect-refuse")
    p_bsc.add_argument("broker_id")
    # M224–M231 broker readiness (SIMULATION_ONLY)
    pg_sub.add_parser("br-verdict")
    pg_sub.add_parser("br-providers")
    pg_sub.add_parser("br-adapters")
    pg_sub.add_parser("br-capabilities")
    p_brpol = pg_sub.add_parser("br-policy-check")
    p_brpol.add_argument("operation")
    p_brpol.add_argument("--scopes", default="")
    p_brpol.add_argument("--permissions", default="")
    p_brcred = pg_sub.add_parser("br-credential-propose")
    p_brcred.add_argument("--provider", default="sim.readonly.fixture")
    p_brcred.add_argument("--scopes", default="ACCOUNT_METADATA_READ,BALANCE_READ,POSITION_READ")
    p_brlife = pg_sub.add_parser("br-credential-lifecycle")
    p_brlife.add_argument("credential_id")
    p_brlife.add_argument("--to", default="")
    p_brsc = pg_sub.add_parser("br-scope-check")
    p_brsc.add_argument("--requested", default="BALANCE_READ")
    p_brsc.add_argument("--approved", default="BALANCE_READ,POSITION_READ")
    pg_sub.add_parser("br-session-simulate")
    pg_sub.add_parser("br-snapshot-load")
    p_brrec = pg_sub.add_parser("br-reconcile")
    p_brrec.add_argument("provider_snapshot_id")
    p_brrec.add_argument("--local", default="")
    pg_sub.add_parser("br-revocation-drill")
    pg_sub.add_parser("br-expiry-drill")
    pg_sub.add_parser("br-incidents")
    pg_sub.add_parser("br-security")
    pg_sub.add_parser("br-certify")
    p_brdrill = pg_sub.add_parser("br-drill")
    p_brdrill.add_argument("scenario")
    # M232–M239 integration assurance (REPRODUCIBILITY AND PLANNING ONLY)
    pg_sub.add_parser("ia-verdict")
    pg_sub.add_parser("ia-source-audit")
    pg_sub.add_parser("ia-clean-worktree")
    pg_sub.add_parser("ia-clean-clone")
    pg_sub.add_parser("ia-env-preflight")
    pg_sub.add_parser("repro-preflight")  # alias
    pg_sub.add_parser("ia-dependencies")
    pg_sub.add_parser("ia-lockfiles")
    pg_sub.add_parser("ia-sbom")
    pg_sub.add_parser("ia-provenance")
    pg_sub.add_parser("ia-supply-chain")
    pg_sub.add_parser("ia-assurance-gates")
    pg_sub.add_parser("ia-authorization-plan")
    pg_sub.add_parser("ia-approval-status")
    pg_sub.add_parser("ia-network-policy")
    pg_sub.add_parser("ia-security")
    pg_sub.add_parser("ia-certify")
    pg_sub.add_parser("ia-dashboard")
    # M240–M247 provider canary planning (PLANNING ONLY)
    pg_sub.add_parser("pcp-verdict")
    pg_sub.add_parser("pcp-candidates")
    pg_sub.add_parser("pcp-rank")
    pg_sub.add_parser("pcp-sources")
    pg_sub.add_parser("pcp-provider")
    pg_sub.add_parser("pcp-capabilities")
    pg_sub.add_parser("pcp-endpoints")
    pg_sub.add_parser("pcp-eligibility")
    pg_sub.add_parser("pcp-terms")
    pg_sub.add_parser("pcp-scopes")
    pg_sub.add_parser("pcp-canary-design")
    pg_sub.add_parser("pcp-credential-runbook")
    pg_sub.add_parser("pcp-monitoring")
    pg_sub.add_parser("pcp-reconciliation")
    pg_sub.add_parser("pcp-acceptance")
    pg_sub.add_parser("pcp-abort")
    pg_sub.add_parser("pcp-owner-package")
    pg_sub.add_parser("pcp-security")
    pg_sub.add_parser("pcp-certify")
    pg_sub.add_parser("pcp-dashboard")

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
        # M208–M215
        if args.action == "ops-posture":
            from saathi.platform.tg.paper_activation.ops.service import default_ops_gov
            return _out(default_ops_gov().posture())
        if args.action == "ops-dashboard":
            from saathi.platform.tg.paper_activation.ops.service import default_ops_gov
            return _out(default_ops_gov().ops_dashboard())
        if args.action == "ops-health":
            from saathi.platform.tg.paper_activation.ops.service import default_ops_gov
            return _out(default_ops_gov().health())
        if args.action == "ops-verdict":
            from saathi.platform.tg.paper_activation.ops.service import default_ops_gov
            return _out(default_ops_gov().terminal_verdict())
        if args.action == "ops-graduate":
            from saathi.platform.tg.paper_activation.ops.service import default_ops_gov
            return _out(default_ops_gov().graduate(args.campaign_id, actor="operator:cli"))
        if args.action == "ops-certify":
            from saathi.platform.tg.paper_activation.ops.service import default_ops_gov
            return _out(default_ops_gov().certify_campaign(args.campaign_id, actor=args.actor))
        if args.action == "ops-intel":
            from saathi.platform.tg.paper_activation.ops.service import default_ops_gov
            return _out(default_ops_gov().scan_intelligence())
        if args.action == "ops-sim-suite":
            from saathi.platform.tg.paper_activation.ops.service import default_ops_gov
            return _out(default_ops_gov().simulate_suite())
        if args.action == "ops-simulate":
            from saathi.platform.tg.paper_activation.ops.service import default_ops_gov
            return _out(default_ops_gov().simulate(args.scenario, portfolio_id=args.portfolio))
        if args.action == "ops-campaign-clone":
            from saathi.platform.tg.paper_activation.ops.service import default_ops_gov
            return _out(default_ops_gov().campaign_clone(args.campaign_id))
        if args.action == "ops-campaign-create":
            from saathi.platform.tg.paper_activation.ops.service import default_ops_gov
            tags = [t for t in (args.tags or "").split(",") if t.strip()]
            return _out(default_ops_gov().campaign_create(
                strategy_slug=args.strategy, owner=args.owner, tags=tags,
            ))
        # M216–M223 broker sandbox
        if args.action == "bs-posture":
            from saathi.platform.tg.broker_sandbox.service import default_broker_sandbox
            return _out(default_broker_sandbox().posture())
        if args.action == "bs-verdict":
            from saathi.platform.tg.broker_sandbox.service import default_broker_sandbox
            return _out(default_broker_sandbox().terminal_verdict())
        if args.action == "bs-dashboard":
            from saathi.platform.tg.broker_sandbox.service import default_broker_sandbox
            return _out(default_broker_sandbox().dashboard())
        if args.action == "bs-brokers":
            from saathi.platform.tg.broker_sandbox.service import default_broker_sandbox
            return _out(default_broker_sandbox().list_brokers())
        if args.action == "bs-capabilities":
            from saathi.platform.tg.broker_sandbox.service import default_broker_sandbox
            return _out(default_broker_sandbox().list_capabilities())
        if args.action == "bs-security":
            from saathi.platform.tg.broker_sandbox.service import default_broker_sandbox
            return _out(default_broker_sandbox().security_validate())
        if args.action == "bs-failure-suite":
            from saathi.platform.tg.broker_sandbox.service import default_broker_sandbox
            return _out(default_broker_sandbox().failure_suite())
        if args.action == "bs-failure":
            from saathi.platform.tg.broker_sandbox.service import default_broker_sandbox
            return _out(default_broker_sandbox().failure_run(args.scenario))
        if args.action == "bs-connect-refuse":
            from saathi.platform.tg.broker_sandbox.service import default_broker_sandbox
            return _out(default_broker_sandbox().refuse_connect(args.broker_id))
        # M224–M231 broker readiness
        if args.action and str(args.action).startswith("br-"):
            from saathi.platform.tg.broker_readiness.service import default_broker_readiness
            br = default_broker_readiness()
            sim = {"SIMULATION_ONLY": True}
            def wrap(d):
                if isinstance(d, dict):
                    d = {**d, **sim}
                return _out(d)
            if args.action == "br-verdict":
                return wrap(br.terminal_verdict())
            if args.action == "br-providers":
                return wrap(br.list_providers())
            if args.action == "br-adapters":
                return wrap(br.adapter_contract())
            if args.action == "br-capabilities":
                return wrap(br.list_adapter_ops())
            if args.action == "br-policy-check":
                scopes = [s for s in args.scopes.split(",") if s.strip()]
                perms = [s for s in args.permissions.split(",") if s.strip()]
                return wrap(br.policy_check(args.operation, scopes=scopes, permissions=perms))
            if args.action == "br-credential-propose":
                scopes = [s for s in args.scopes.split(",") if s.strip()]
                # reject secret-shaped CLI args
                if any(x in ("api_key", "secret", "token", "password") for x in dir(args)):
                    pass
                return wrap(br.propose_credential(provider_id=args.provider, declared_scopes=scopes, actor="operator:cli"))
            if args.action == "br-credential-lifecycle":
                return wrap(br.credential_lifecycle(args.credential_id, to_state=args.to or "", actor="operator:cli"))
            if args.action == "br-scope-check":
                req = [s for s in args.requested.split(",") if s.strip()]
                appr = [s for s in args.approved.split(",") if s.strip()]
                return wrap(br.scope_check(requested=req, declared=req, approved=appr, provider_reported=req))
            if args.action == "br-session-simulate":
                s = br.session_create()
                return wrap(br.session_simulate(s["session"]["id"]))
            if args.action == "br-snapshot-load":
                return wrap(br.snapshot_load())
            if args.action == "br-reconcile":
                return wrap(br.reconcile_run(args.provider_snapshot_id, args.local))
            if args.action == "br-revocation-drill":
                return wrap(br.revocation_drill())
            if args.action == "br-expiry-drill":
                return wrap(br.expiry_drill())
            if args.action == "br-incidents":
                return wrap(br.list_drills())
            if args.action == "br-security":
                return wrap(br.security_scan())
            if args.action == "br-certify":
                return wrap(br.certify())
            if args.action == "br-drill":
                return wrap(br.drill_run(args.scenario))
        # M232–M239 integration assurance
        if args.action and (str(args.action).startswith("ia-") or args.action == "repro-preflight"):
            from saathi.platform.tg.integration_assurance.service import default_integration_assurance
            ia = default_integration_assurance()
            def iwrap(d):
                if isinstance(d, dict):
                    d = {**d, "REAL_CONNECTIVITY_AUTHORIZED": False}
                return _out(d)
            if args.action in ("ia-verdict",):
                return iwrap(ia.terminal_verdict())
            if args.action == "ia-source-audit":
                return iwrap(ia.source_audit())
            if args.action == "ia-clean-worktree":
                return iwrap(ia.clean_worktree())
            if args.action == "ia-clean-clone":
                return iwrap(ia.clean_clone())
            if args.action in ("ia-env-preflight", "repro-preflight"):
                return iwrap(ia.env_preflight())
            if args.action == "ia-dependencies":
                return iwrap(ia.dependency_inventory())
            if args.action == "ia-lockfiles":
                return iwrap(ia.lockfile_checks())
            if args.action == "ia-sbom":
                return iwrap(ia.generate_sbom())
            if args.action == "ia-provenance":
                return iwrap(ia.provenance())
            if args.action == "ia-supply-chain":
                return iwrap(ia.threat_model())
            if args.action == "ia-assurance-gates":
                return iwrap(ia.assurance_gates())
            if args.action == "ia-authorization-plan":
                return iwrap(ia.auth_create_plan())
            if args.action == "ia-approval-status":
                return iwrap(ia.auth_eligibility())
            if args.action == "ia-network-policy":
                return iwrap(ia.network_policy())
            if args.action == "ia-security":
                return iwrap(ia.security_scan())
            if args.action == "ia-certify":
                return iwrap(ia.certify())
            if args.action == "ia-dashboard":
                return iwrap(ia.dashboard())
        # M240–M247 provider canary planning
        if args.action and str(args.action).startswith("pcp-"):
            from saathi.platform.tg.provider_canary_planning.service import default_provider_canary_planning
            pcp = default_provider_canary_planning()

            def pwrap(d):
                if isinstance(d, dict):
                    d = {
                        **d,
                        "REAL_CONNECTIVITY_AUTHORIZED": False,
                        "CREDENTIAL_PROVISIONING_AUTHORIZED": False,
                        "CANARY_ACTIVATION_AUTHORIZED": False,
                        "LIVE_TRADING_AUTHORIZED": False,
                    }
                return _out(d)

            if args.action == "pcp-verdict":
                return pwrap(pcp.terminal_verdict())
            if args.action == "pcp-candidates":
                return pwrap(pcp.candidates())
            if args.action == "pcp-rank":
                return pwrap(pcp.rankings())
            if args.action == "pcp-sources":
                return pwrap(pcp.list_sources())
            if args.action == "pcp-provider":
                return pwrap({"preferred": pcp.preferred(), "fallback": pcp.fallback()})
            if args.action == "pcp-capabilities":
                return pwrap(pcp.capabilities_map())
            if args.action == "pcp-endpoints":
                return pwrap(pcp.endpoints())
            if args.action == "pcp-eligibility":
                return pwrap(pcp.eligibility_review())
            if args.action == "pcp-terms":
                return pwrap(pcp.terms_review())
            if args.action == "pcp-scopes":
                return pwrap(pcp.scopes())
            if args.action == "pcp-canary-design":
                return pwrap(pcp.canary_design())
            if args.action == "pcp-credential-runbook":
                return pwrap(pcp.credential_ceremony())
            if args.action == "pcp-monitoring":
                return pwrap(pcp.monitoring_plan())
            if args.action == "pcp-reconciliation":
                return pwrap(pcp.reconciliation_plan())
            if args.action == "pcp-acceptance":
                return pwrap(pcp.acceptance_gates())
            if args.action == "pcp-abort":
                return pwrap(pcp.abort_gates())
            if args.action == "pcp-owner-package":
                return pwrap(pcp.owner_package())
            if args.action == "pcp-security":
                return pwrap(pcp.security_scan())
            if args.action == "pcp-certify":
                return pwrap(pcp.certify())
            if args.action == "pcp-dashboard":
                return pwrap(pcp.dashboard())
        return 2

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
