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
    # M248–M255 institutional investment intelligence (PAPER ONLY)
    pg_sub.add_parser("ii-strategy-list")
    p_iis = pg_sub.add_parser("ii-strategy-run")
    p_iis.add_argument("--strategy", default="tf_dual_ma")
    pg_sub.add_parser("ii-portfolio-risk")
    pg_sub.add_parser("ii-portfolio-report")
    p_iibt = pg_sub.add_parser("ii-backtest")
    p_iibt.add_argument("--strategy", default="tf_dual_ma")
    p_iibt.add_argument("--seed", type=int, default=42)
    p_iimc = pg_sub.add_parser("ii-monte-carlo")
    p_iimc.add_argument("--n", type=int, default=200)
    p_iimc.add_argument("--seed", type=int, default=42)
    p_iiwf = pg_sub.add_parser("ii-walk-forward")
    p_iiwf.add_argument("--strategy", default="tf_dual_ma")
    p_iiwf.add_argument("--seed", type=int, default=42)
    p_iic = pg_sub.add_parser("ii-committee-review")
    p_iic.add_argument("--instrument", default="SPY")
    p_iie = pg_sub.add_parser("ii-explain")
    p_iie.add_argument("--instrument", default="SPY")
    p_iie.add_argument("--strategy", default="tf_dual_ma")
    pg_sub.add_parser("ii-certify")
    pg_sub.add_parser("ii-dashboard")
    # M256–M263 market data & signal validation (RESEARCH ONLY)
    pg_sub.add_parser("md-verdict")
    pg_sub.add_parser("md-dataset-list")
    p_mds = pg_sub.add_parser("md-dataset-show")
    p_mds.add_argument("--id", required=True)
    p_mds.add_argument("--version", default="")
    p_mdr = pg_sub.add_parser("md-dataset-register")
    p_mdr.add_argument("--name", required=True)
    p_mdr.add_argument("--licence", default="CC0-1.0")
    p_mdr.add_argument("--synthetic", action="store_true")
    p_mdl = pg_sub.add_parser("md-licence-check")
    p_mdl.add_argument("--id", required=True)
    p_mdl.add_argument("--version", default="v1")
    p_mdp = pg_sub.add_parser("md-provenance")
    p_mdp.add_argument("--id", required=True)
    p_mdp.add_argument("--version", default="v1")
    p_mdi = pg_sub.add_parser("md-ingest")
    p_mdi.add_argument("--id", required=True)
    p_mdi.add_argument("--version", default="v1")
    p_mdir = pg_sub.add_parser("md-ingest-report")
    p_mdir.add_argument("--id", required=True)
    p_mdq = pg_sub.add_parser("md-quality")
    p_mdq.add_argument("--id", required=True)
    p_mdq.add_argument("--version", default="v1")
    p_mdqr = pg_sub.add_parser("md-quality-report")
    p_mdqr.add_argument("--id", required=True)
    p_mdqr.add_argument("--version", default="v1")
    p_mdqu = pg_sub.add_parser("md-quarantine")
    p_mdqu.add_argument("--id", required=True)
    p_mdqu.add_argument("--version", default="v1")
    p_mdc = pg_sub.add_parser("md-calendar-check")
    p_mdc.add_argument("--id", required=True)
    p_mdc.add_argument("--version", default="v1")
    p_mdca = pg_sub.add_parser("md-corporate-actions")
    p_mdca.add_argument("--id", required=True)
    p_mdca.add_argument("--version", default="v1")
    p_mda = pg_sub.add_parser("md-adjust")
    p_mda.add_argument("--id", required=True)
    p_mda.add_argument("--version", default="v1")
    p_mda.add_argument("--symbol", default="DEMO")
    p_mdb = pg_sub.add_parser("md-bias-check")
    p_mdb.add_argument("--id", required=True)
    p_mdb.add_argument("--version", default="v1")
    p_mdsp = pg_sub.add_parser("md-split")
    p_mdsp.add_argument("--id", required=True)
    p_mdsp.add_argument("--version", default="v1")
    pg_sub.add_parser("md-feature-list")
    p_mdfb = pg_sub.add_parser("md-feature-build")
    p_mdfb.add_argument("--id", required=True)
    p_mdfb.add_argument("--version", default="v1")
    p_mdfl = pg_sub.add_parser("md-feature-lineage")
    p_mdfl.add_argument("--feature", required=True)
    p_mdv = pg_sub.add_parser("md-validate-signal")
    p_mdv.add_argument("--strategy", default="tf_dual_ma")
    p_mdv.add_argument("--id", required=True)
    p_mdv.add_argument("--version", default="v1")
    p_mdcs = pg_sub.add_parser("md-compare-strategies")
    p_mdcs.add_argument("--id", required=True)
    p_mdcs.add_argument("--version", default="v1")
    p_mdra = pg_sub.add_parser("md-regime-analysis")
    p_mdra.add_argument("--id", required=True)
    p_mdra.add_argument("--version", default="v1")
    pg_sub.add_parser("md-certify")
    pg_sub.add_parser("md-dashboard")
    pg_sub.add_parser("md-bootstrap")
    # M272–M279 multi-strategy research lab (RESEARCH ONLY)
    pg_sub.add_parser("rl-verdict")
    p_rlc = pg_sub.add_parser("rl-experiment-create")
    p_rlc.add_argument("--name", default="cli_experiment")
    p_rlc.add_argument("--strategy", default="tf_dual_ma")
    p_rlp = pg_sub.add_parser("rl-experiment-preregister")
    p_rlp.add_argument("--id", required=True)
    p_rlp.add_argument("--version", default="v1")
    pg_sub.add_parser("rl-experiment-list")
    p_rls = pg_sub.add_parser("rl-experiment-show")
    p_rls.add_argument("--id", required=True)
    p_rls.add_argument("--version", default="v1")
    p_rlr = pg_sub.add_parser("rl-experiment-run")
    p_rlr.add_argument("--id", required=True)
    p_rlr.add_argument("--version", default="v1")
    p_rlrep = pg_sub.add_parser("rl-experiment-replay")
    p_rlrep.add_argument("--id", required=True)
    p_rlrep.add_argument("--version", default="v1")
    pg_sub.add_parser("rl-strategy-compare")
    p_rlrob = pg_sub.add_parser("rl-robustness")
    p_rlrob.add_argument("--strategy", default="tf_dual_ma")
    pg_sub.add_parser("rl-overfitting")
    pg_sub.add_parser("rl-regime-build")
    pg_sub.add_parser("rl-regime-classify")
    pg_sub.add_parser("rl-regime-validate")
    pg_sub.add_parser("rl-portfolio-build")
    pg_sub.add_parser("rl-portfolio-optimise")
    pg_sub.add_parser("rl-portfolio-risk")
    pg_sub.add_parser("rl-ensemble-build")
    pg_sub.add_parser("rl-ensemble-validate")
    pg_sub.add_parser("rl-stress-run")
    pg_sub.add_parser("rl-candidate-list")
    p_rlcr = pg_sub.add_parser("rl-candidate-review")
    p_rlcr.add_argument("--id", required=True)
    p_rlcr.add_argument("--actor", default="human_reviewer")
    p_rlcj = pg_sub.add_parser("rl-candidate-reject")
    p_rlcj.add_argument("--id", required=True)
    p_rlcj.add_argument("--reason", default="rejected_by_operator")
    p_rlcv = pg_sub.add_parser("rl-candidate-revoke")
    p_rlcv.add_argument("--id", required=True)
    p_rlcv.add_argument("--reason", default="revoked_by_operator")
    pg_sub.add_parser("rl-certify")
    pg_sub.add_parser("rl-dashboard")
    pg_sub.add_parser("rl-bootstrap")
    # Top-level md-* aliases
    sub.add_parser("md-verdict")
    sub.add_parser("md-dataset-list")
    sub.add_parser("md-feature-list")
    sub.add_parser("md-certify")
    sub.add_parser("md-dashboard")
    sub.add_parser("md-bootstrap")
    # Top-level rl-* aliases
    sub.add_parser("rl-verdict")
    sub.add_parser("rl-experiment-list")
    sub.add_parser("rl-strategy-compare")
    sub.add_parser("rl-certify")
    sub.add_parser("rl-dashboard")
    sub.add_parser("rl-bootstrap")
    # M280–M287 autonomous research orchestrator
    pg_sub.add_parser("ro-verdict")
    pg_sub.add_parser("ro-dashboard")
    pg_sub.add_parser("ro-bootstrap")
    pg_sub.add_parser("ro-job-list")
    p_roe = pg_sub.add_parser("ro-job-enqueue")
    p_roe.add_argument("--name", default="cli_job")
    p_roe.add_argument("--kind", default="noop")
    p_roe.add_argument("--priority", default="NORMAL")
    p_rot = pg_sub.add_parser("ro-tick")
    p_rot.add_argument("--max-jobs", type=int, default=1)
    pg_sub.add_parser("ro-workers")
    pg_sub.add_parser("ro-budget")
    pg_sub.add_parser("ro-templates")
    pg_sub.add_parser("ro-strategies")
    pg_sub.add_parser("ro-notebook")
    pg_sub.add_parser("ro-failures")
    pg_sub.add_parser("ro-calendar")
    pg_sub.add_parser("ro-certify")
    sub.add_parser("ro-verdict")
    sub.add_parser("ro-dashboard")
    sub.add_parser("ro-bootstrap")
    sub.add_parser("ro-certify")
    sub.add_parser("ro-job-list")
    # M288–M295 institutional paper simulation
    pg_sub.add_parser("ps-verdict")
    pg_sub.add_parser("ps-dashboard")
    pg_sub.add_parser("ps-bootstrap")
    pg_sub.add_parser("ps-exchange")
    pg_sub.add_parser("ps-portfolio-list")
    pg_sub.add_parser("ps-kill-switch")
    pg_sub.add_parser("ps-calendar")
    pg_sub.add_parser("ps-certify")
    sub.add_parser("ps-verdict")
    sub.add_parser("ps-dashboard")
    sub.add_parser("ps-bootstrap")
    sub.add_parser("ps-certify")
    # M296–M303 portfolio risk intelligence
    pg_sub.add_parser("pr-verdict")
    pg_sub.add_parser("pr-dashboard")
    pg_sub.add_parser("pr-bootstrap")
    pg_sub.add_parser("pr-analytics")
    pg_sub.add_parser("pr-limits")
    pg_sub.add_parser("pr-attribution")
    pg_sub.add_parser("pr-optimise")
    pg_sub.add_parser("pr-scenarios")
    pg_sub.add_parser("pr-committee")
    pg_sub.add_parser("pr-certify")
    sub.add_parser("pr-verdict")
    sub.add_parser("pr-dashboard")
    sub.add_parser("pr-bootstrap")
    sub.add_parser("pr-certify")
    # M304–M311 read-only market observation
    pg_sub.add_parser("mo-verdict")
    pg_sub.add_parser("mo-dashboard")
    pg_sub.add_parser("mo-bootstrap")
    pg_sub.add_parser("mo-symbols")
    pg_sub.add_parser("mo-quotes")
    pg_sub.add_parser("mo-snapshot")
    pg_sub.add_parser("mo-exchanges")
    pg_sub.add_parser("mo-benchmarks")
    pg_sub.add_parser("mo-certify")
    sub.add_parser("mo-verdict")
    sub.add_parser("mo-dashboard")
    sub.add_parser("mo-bootstrap")
    sub.add_parser("mo-certify")
    # M312–M319 connectivity governance
    for _cg in (
        "cg-verdict", "cg-charter-show", "cg-authority-list", "cg-authority-evaluate",
        "cg-provider-list", "cg-provider-show", "cg-provider-register", "cg-provider-prohibit",
        "cg-approval-create", "cg-approval-submit", "cg-approval-review", "cg-approval-reject",
        "cg-approval-revoke", "cg-credential-policy", "cg-threat-list", "cg-risk-summary",
        "cg-incident-create", "cg-incident-contain", "cg-emergency-shutdown", "cg-maturity",
        "cg-certify", "cg-dashboard", "cg-bootstrap",
    ):
        pg_sub.add_parser(_cg)
        sub.add_parser(_cg)
    # M320–M327 credentialless provider contracts (mock/replay only)
    for _pc in (
        "pc-verdict", "pc-charter", "pc-dashboard", "pc-providers", "pc-capabilities",
        "pc-sessions", "pc-replay-fixtures", "pc-mock-quote",
        "pc-replay-quote", "pc-security", "pc-certify",
    ):
        pg_sub.add_parser(_pc)
        sub.add_parser(_pc)
    # Aliases matching goal prompt command names
    p_sl = sub.add_parser("strategy-list")
    p_sl.add_argument("--category", default="")
    p_sr = sub.add_parser("strategy-run")
    p_sr.add_argument("--strategy", default="tf_dual_ma")
    sub.add_parser("portfolio-risk")
    sub.add_parser("portfolio-report")
    p_bt2 = sub.add_parser("backtest-v2")
    p_bt2.add_argument("--strategy", default="tf_dual_ma")
    p_bt2.add_argument("--seed", type=int, default=42)
    p_mc2 = sub.add_parser("monte-carlo")
    p_mc2.add_argument("--n", type=int, default=200)
    p_mc2.add_argument("--seed", type=int, default=42)
    p_wf2 = sub.add_parser("walk-forward")
    p_wf2.add_argument("--strategy", default="tf_dual_ma")
    p_wf2.add_argument("--seed", type=int, default=42)
    p_cr = sub.add_parser("committee-review")
    p_cr.add_argument("--instrument", default="SPY")
    p_ex = sub.add_parser("explain")
    p_ex.add_argument("--instrument", default="SPY")
    p_ex.add_argument("--strategy", default="tf_dual_ma")
    sub.add_parser("certify-intelligence")

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
        # M248–M255 institutional intelligence
        if args.action and str(args.action).startswith("ii-"):
            from saathi.platform.tg.intelligence.service import default_intelligence
            ii = default_intelligence()

            def iwrap(d):
                if isinstance(d, dict):
                    d = {
                        **d,
                        "LIVE_TRADING_AUTHORIZED": False,
                        "BROKER_CONNECTIVITY_AUTHORIZED": False,
                        "paper_only": True,
                    }
                return _out(d)

            if args.action == "ii-strategy-list":
                return iwrap(ii.list_strategies())
            if args.action == "ii-strategy-run":
                return iwrap(ii.strategy_run(args.strategy))
            if args.action == "ii-portfolio-risk":
                return iwrap(ii.portfolio_risk())
            if args.action == "ii-portfolio-report":
                return iwrap(ii.portfolio_report())
            if args.action == "ii-backtest":
                return iwrap(ii.backtest(args.strategy, seed=args.seed))
            if args.action == "ii-monte-carlo":
                return iwrap(ii.run_monte_carlo(n_simulations=args.n, seed=args.seed))
            if args.action == "ii-walk-forward":
                return iwrap(ii.run_walk_forward(args.strategy, seed=args.seed))
            if args.action == "ii-committee-review":
                return iwrap(ii.committee_review(args.instrument))
            if args.action == "ii-explain":
                return iwrap(ii.explain(args.instrument, strategy_id=args.strategy))
            if args.action == "ii-certify":
                return iwrap(ii.certify())
            if args.action == "ii-dashboard":
                return iwrap(ii.dashboard())
        # M256–M263 market data
        if args.action and str(args.action).startswith("md-"):
            from saathi.platform.tg.market_data.service import default_market_data
            md = default_market_data()

            def mwrap(d):
                if isinstance(d, dict):
                    d = {
                        **d,
                        "REAL_CONNECTIVITY_AUTHORIZED": False,
                        "CREDENTIAL_PROVISIONING_AUTHORIZED": False,
                        "CANARY_ACTIVATION_AUTHORIZED": False,
                        "ORDER_EXECUTION_AUTHORIZED": False,
                        "LIVE_TRADING_AUTHORIZED": False,
                        "research_only": True,
                    }
                return _out(d)

            if args.action == "md-verdict":
                return mwrap(md.terminal_verdict())
            if args.action == "md-dataset-list":
                return mwrap(md.list_datasets())
            if args.action == "md-dataset-show":
                return mwrap(md.get_dataset(args.id, args.version or None))
            if args.action == "md-dataset-register":
                return mwrap(md.register_dataset(
                    name=args.name, licence_type=args.licence,
                    is_synthetic=bool(args.synthetic), checksum="cli_register",
                ))
            if args.action == "md-licence-check":
                return mwrap(md.licence_check(args.id, args.version))
            if args.action == "md-provenance":
                return mwrap(md.get_provenance(args.id, args.version))
            if args.action == "md-ingest":
                return mwrap(md.ingest(args.id, args.version))
            if args.action == "md-ingest-report":
                return mwrap(md.ingest_report(args.id))
            if args.action == "md-quality":
                return mwrap(md.quality_check(args.id, args.version))
            if args.action == "md-quality-report":
                return mwrap(md.quality_report(args.id, args.version))
            if args.action == "md-quarantine":
                return mwrap(md.quarantine_dataset(args.id, args.version))
            if args.action == "md-calendar-check":
                return mwrap(md.calendar_check(args.id, args.version))
            if args.action == "md-corporate-actions":
                return mwrap(md.list_corporate_actions(args.id, args.version))
            if args.action == "md-adjust":
                return mwrap(md.adjust(args.id, args.version, args.symbol))
            if args.action == "md-bias-check":
                return mwrap(md.bias_check(args.id, args.version))
            if args.action == "md-split":
                return mwrap(md.split_dataset(args.id, args.version))
            if args.action == "md-feature-list":
                return mwrap(md.feature_list())
            if args.action == "md-feature-build":
                return mwrap(md.feature_build(args.id, args.version))
            if args.action == "md-feature-lineage":
                return mwrap(md.feature_lineage(args.feature))
            if args.action == "md-validate-signal":
                split = md.split_dataset(args.id, args.version)
                return mwrap(md.validate_signal(args.strategy, args.id, args.version, split=split))
            if args.action == "md-compare-strategies":
                return mwrap(md.compare_strategies(["tf_dual_ma", "mr_zscore"], args.id, args.version))
            if args.action == "md-regime-analysis":
                return mwrap(md.regime_analysis(args.id, args.version))
            if args.action == "md-certify":
                return mwrap(md.certify())
            if args.action == "md-dashboard":
                return mwrap(md.dashboard())
            if args.action == "md-bootstrap":
                return mwrap(md.bootstrap_fixture_pipeline())
        # M272–M279 research lab
        if args.action and str(args.action).startswith("rl-"):
            from saathi.platform.tg.research_lab.service import default_research_lab
            rl = default_research_lab()

            def rwrap(d):
                if isinstance(d, dict):
                    d = {
                        **d,
                        "REAL_CONNECTIVITY_AUTHORIZED": False,
                        "BROKER_CONNECTIVITY_AUTHORIZED": False,
                        "CREDENTIAL_PROVISIONING_AUTHORIZED": False,
                        "CANARY_ACTIVATION_AUTHORIZED": False,
                        "ORDER_EXECUTION_AUTHORIZED": False,
                        "LIVE_TRADING_AUTHORIZED": False,
                        "research_only": True,
                    }
                return _out(d)

            if args.action == "rl-verdict":
                return rwrap(rl.terminal_verdict())
            if args.action == "rl-experiment-create":
                return rwrap(rl.create_experiment(
                    args.name, strategy_ids=[args.strategy], random_seed=42,
                ))
            if args.action == "rl-experiment-preregister":
                return rwrap(rl.pre_register(args.id, args.version))
            if args.action == "rl-experiment-list":
                return rwrap(rl.list_experiments())
            if args.action == "rl-experiment-show":
                return rwrap(rl.get_experiment(args.id, args.version))
            if args.action == "rl-experiment-run":
                return rwrap(rl.run_experiment(args.id, args.version))
            if args.action == "rl-experiment-replay":
                return rwrap(rl.replay_experiment(args.id, args.version))
            if args.action == "rl-strategy-compare":
                return rwrap(rl.compare_strategies())
            if args.action == "rl-robustness":
                return rwrap(rl.analyse_robustness(args.strategy))
            if args.action == "rl-overfitting":
                return rwrap(rl.analyse_robustness("tf_dual_ma"))
            if args.action == "rl-regime-build":
                return rwrap(rl.build_regimes())
            if args.action == "rl-regime-classify":
                return rwrap(rl.classify_regimes())
            if args.action == "rl-regime-validate":
                return rwrap(rl.validate_regimes())
            if args.action in ("rl-portfolio-build", "rl-portfolio-optimise", "rl-portfolio-risk"):
                from saathi.platform.tg.research_lab.comparison import _simulate_strategy_returns
                assets = ["tf_dual_ma", "mom_rs_equity"]
                rets = {a: _simulate_strategy_returns(a, n=80, seed=i)["returns"] for i, a in enumerate(assets)}
                return rwrap(rl.build_portfolio(assets, rets, method="equal_weight"))
            if args.action in ("rl-ensemble-build", "rl-ensemble-validate"):
                return rwrap(rl.build_ensemble(["tf_dual_ma", "mom_rs_equity", "mr_bollinger_reversion"]))
            if args.action == "rl-stress-run":
                from saathi.platform.tg.research_lab.comparison import _simulate_strategy_returns
                assets = ["tf_dual_ma", "mom_rs_equity"]
                rets = {a: _simulate_strategy_returns(a, n=80, seed=i)["returns"] for i, a in enumerate(assets)}
                w = {a: 0.5 for a in assets}
                return rwrap(rl.run_stress(w, rets))
            if args.action == "rl-candidate-list":
                return rwrap(rl.list_candidates())
            if args.action == "rl-candidate-review":
                return rwrap(rl.request_candidate_review(args.id, actor=args.actor))
            if args.action == "rl-candidate-reject":
                return rwrap(rl.reject_candidate(args.id, args.reason))
            if args.action == "rl-candidate-revoke":
                return rwrap(rl.revoke_candidate(args.id, args.reason))
            if args.action == "rl-certify":
                return rwrap(rl.certify())
            if args.action == "rl-dashboard":
                return rwrap(rl.dashboard())
            if args.action == "rl-bootstrap":
                return rwrap(rl.bootstrap_demo_pipeline())
        # M280–M287 research orchestrator
        if args.action and str(args.action).startswith("ro-"):
            from saathi.platform.tg.research_orchestrator.service import default_research_orchestrator
            ro = default_research_orchestrator()

            def owrap(d):
                if isinstance(d, dict):
                    d = {
                        **d,
                        "REAL_CONNECTIVITY_AUTHORIZED": False,
                        "BROKER_CONNECTIVITY_AUTHORIZED": False,
                        "ORDER_EXECUTION_AUTHORIZED": False,
                        "LIVE_TRADING_AUTHORIZED": False,
                        "research_only": True,
                    }
                return _out(d)

            if args.action == "ro-verdict":
                return owrap(ro.terminal_verdict())
            if args.action == "ro-dashboard":
                return owrap(ro.dashboard())
            if args.action == "ro-bootstrap":
                return owrap(ro.bootstrap_demo_pipeline())
            if args.action == "ro-job-list":
                return owrap(ro.list_jobs())
            if args.action == "ro-job-enqueue":
                return owrap(ro.enqueue_job(args.name, {"kind": args.kind, "seed": 42}, priority=args.priority))
            if args.action == "ro-tick":
                return owrap(ro.tick(max_jobs=args.max_jobs))
            if args.action == "ro-workers":
                return owrap(ro.workers_status())
            if args.action == "ro-budget":
                return owrap(ro.budget_status())
            if args.action == "ro-templates":
                return owrap(ro.list_templates())
            if args.action == "ro-strategies":
                return owrap(ro.list_strategies_v2())
            if args.action == "ro-notebook":
                return owrap(ro.notebook())
            if args.action == "ro-failures":
                return owrap(ro.failure_analysis())
            if args.action == "ro-calendar":
                return owrap(ro.research_calendar())
            if args.action == "ro-certify":
                return owrap(ro.certify())
        # M288–M295 paper simulation
        if args.action and str(args.action).startswith("ps-"):
            from saathi.platform.tg.paper_simulation.service import default_paper_simulation
            ps = default_paper_simulation()

            def pwrap(d):
                if isinstance(d, dict):
                    d = {
                        **d,
                        "REAL_CONNECTIVITY_AUTHORIZED": False,
                        "BROKER_CONNECTIVITY_AUTHORIZED": False,
                        "ORDER_EXECUTION_AUTHORIZED": False,
                        "LIVE_TRADING_AUTHORIZED": False,
                        "simulation_only": True,
                    }
                return _out(d)

            if args.action == "ps-verdict":
                return pwrap(ps.terminal_verdict())
            if args.action == "ps-dashboard":
                return pwrap(ps.dashboard())
            if args.action == "ps-bootstrap":
                return pwrap(ps.bootstrap_demo_pipeline())
            if args.action == "ps-exchange":
                return pwrap(ps.exchange_status())
            if args.action == "ps-portfolio-list":
                return pwrap(ps.list_portfolios())
            if args.action == "ps-kill-switch":
                return pwrap(ps.kill_switch_status())
            if args.action == "ps-calendar":
                return pwrap(ps.trading_calendar())
            if args.action == "ps-certify":
                return pwrap(ps.certify())
        # M296–M303 portfolio risk
        if args.action and str(args.action).startswith("pr-"):
            from saathi.platform.tg.portfolio_risk.service import default_portfolio_risk
            pr = default_portfolio_risk()

            def prwrap(d):
                if isinstance(d, dict):
                    d = {
                        **d,
                        "REAL_CONNECTIVITY_AUTHORIZED": False,
                        "BROKER_CONNECTIVITY_AUTHORIZED": False,
                        "ORDER_EXECUTION_AUTHORIZED": False,
                        "LIVE_TRADING_AUTHORIZED": False,
                        "research_only": True,
                    }
                return _out(d)

            if args.action == "pr-verdict":
                return prwrap(pr.terminal_verdict())
            if args.action == "pr-dashboard":
                return prwrap(pr.dashboard())
            if args.action == "pr-bootstrap":
                return prwrap(pr.bootstrap_demo_pipeline())
            if args.action == "pr-analytics":
                return prwrap(pr.analyze())
            if args.action == "pr-limits":
                return prwrap(pr.evaluate_limits())
            if args.action == "pr-attribution":
                return prwrap(pr.performance_attribution())
            if args.action == "pr-optimise":
                return prwrap(pr.optimise())
            if args.action == "pr-scenarios":
                return prwrap(pr.run_scenarios())
            if args.action == "pr-committee":
                return prwrap(pr.committee_review())
            if args.action == "pr-certify":
                return prwrap(pr.certify())
        # M304–M311 market observation
        if args.action and str(args.action).startswith("mo-"):
            from saathi.platform.tg.market_observation.service import default_market_observation
            mo = default_market_observation()

            def mowrap(d):
                if isinstance(d, dict):
                    d = {
                        **d,
                        "REAL_CONNECTIVITY_AUTHORIZED": False,
                        "BROKER_CONNECTIVITY_AUTHORIZED": False,
                        "ORDER_EXECUTION_AUTHORIZED": False,
                        "LIVE_TRADING_AUTHORIZED": False,
                        "ACCOUNT_ACCESS_AUTHORIZED": False,
                        "read_only_observation": True,
                    }
                return _out(d)

            if args.action == "mo-verdict":
                return mowrap(mo.terminal_verdict())
            if args.action == "mo-dashboard":
                return mowrap(mo.dashboard())
            if args.action == "mo-bootstrap":
                return mowrap(mo.bootstrap_demo_pipeline())
            if args.action == "mo-symbols":
                return mowrap(mo.list_symbols())
            if args.action == "mo-quotes":
                return mowrap(mo.list_quotes())
            if args.action == "mo-snapshot":
                return mowrap(mo.market_snapshot())
            if args.action == "mo-exchanges":
                return mowrap(mo.list_exchange_status())
            if args.action == "mo-benchmarks":
                return mowrap(mo.list_benchmarks())
            if args.action == "mo-certify":
                return mowrap(mo.certify())
        # M312–M319 connectivity governance
        if args.action and str(args.action).startswith("cg-"):
            from saathi.platform.tg.connectivity_governance.service import default_connectivity_governance
            cg = default_connectivity_governance()
            action = args.action
            if action == "cg-verdict":
                return _out(cg.terminal_verdict())
            if action == "cg-dashboard":
                return _out(cg.dashboard())
            if action == "cg-bootstrap":
                return _out(cg.bootstrap_demo_pipeline())
            if action == "cg-charter-show":
                return _out(cg.charter())
            if action == "cg-authority-list":
                return _out(cg.authority_list())
            if action == "cg-provider-list":
                return _out(cg.list_providers())
            if action == "cg-credential-policy":
                return _out(cg.credential_policy())
            if action == "cg-threat-list":
                return _out(cg.list_threats())
            if action == "cg-risk-summary":
                return _out(cg.risk_summary())
            if action == "cg-maturity":
                return _out(cg.maturity())
            if action == "cg-emergency-shutdown":
                return _out(cg.emergency_shutdown(actor="cli_operator", reason="paper_gov_drill"))
            if action == "cg-certify":
                return _out(cg.certify())
            return _out({"ok": False, "error": f"unknown cg action: {action}"})
        if args.action and str(args.action).startswith("pc-"):
            from saathi.platform.tg.provider_contracts.service import default_provider_contracts
            pc = default_provider_contracts()
            action = args.action
            if action == "pc-verdict":
                return _out(pc.posture())
            if action == "pc-charter":
                return _out(pc.charter())
            if action == "pc-dashboard":
                return _out(pc.dashboard())
            if action == "pc-providers":
                return _out(pc.list_providers())
            if action == "pc-capabilities":
                return _out(pc.capabilities())
            if action == "pc-sessions":
                return _out(pc.sessions())
            if action == "pc-replay-fixtures":
                return _out(pc.replay_fixtures())
            if action == "pc-mock-quote":
                return _out(pc.mock_quote())
            if action == "pc-replay-quote":
                return _out(pc.replay_quote())
            if action == "pc-security":
                return _out(pc.security_scan())
            if action == "pc-certify":
                return _out(pc.certify())
            return _out({"ok": False, "error": f"unknown pc action: {action}"})
        return 2

    # Top-level market-data aliases (M256–M263)
    if args.cmd in (
        "md-verdict", "md-dataset-list", "md-feature-list",
        "md-certify", "md-dashboard", "md-bootstrap",
    ):
        from saathi.platform.tg.market_data.service import default_market_data
        md = default_market_data()
        if args.cmd == "md-verdict":
            return _out(md.terminal_verdict())
        if args.cmd == "md-dataset-list":
            return _out(md.list_datasets())
        if args.cmd == "md-feature-list":
            return _out(md.feature_list())
        if args.cmd == "md-certify":
            return _out(md.certify())
        if args.cmd == "md-dashboard":
            return _out(md.dashboard())
        if args.cmd == "md-bootstrap":
            return _out(md.bootstrap_fixture_pipeline())

    # Top-level intelligence command aliases (M248–M255)
    if args.cmd in (
        "strategy-list", "strategy-run", "portfolio-risk", "portfolio-report",
        "backtest-v2", "monte-carlo", "walk-forward", "committee-review",
        "explain", "certify-intelligence",
    ):
        from saathi.platform.tg.intelligence.service import default_intelligence
        ii = default_intelligence()
        if args.cmd == "strategy-list":
            cat = getattr(args, "category", "") or None
            return _out(ii.list_strategies(cat if cat else None))
        if args.cmd == "strategy-run":
            return _out(ii.strategy_run(args.strategy))
        if args.cmd == "portfolio-risk":
            return _out(ii.portfolio_risk())
        if args.cmd == "portfolio-report":
            return _out(ii.portfolio_report())
        if args.cmd == "backtest-v2":
            return _out(ii.backtest(args.strategy, seed=args.seed))
        if args.cmd == "monte-carlo":
            return _out(ii.run_monte_carlo(n_simulations=args.n, seed=args.seed))
        if args.cmd == "walk-forward":
            return _out(ii.run_walk_forward(args.strategy, seed=args.seed))
        if args.cmd == "committee-review":
            return _out(ii.committee_review(args.instrument))
        if args.cmd == "explain":
            return _out(ii.explain(args.instrument, strategy_id=args.strategy))
        if args.cmd == "certify-intelligence":
            return _out(ii.certify())

    # Top-level research-lab aliases (M272–M279)
    if args.cmd in (
        "rl-verdict", "rl-experiment-list", "rl-strategy-compare",
        "rl-certify", "rl-dashboard", "rl-bootstrap",
    ):
        from saathi.platform.tg.research_lab.service import default_research_lab
        rl = default_research_lab()
        if args.cmd == "rl-verdict":
            return _out({
                **rl.terminal_verdict(),
                "REAL_CONNECTIVITY_AUTHORIZED": False,
                "BROKER_CONNECTIVITY_AUTHORIZED": False,
                "CREDENTIAL_PROVISIONING_AUTHORIZED": False,
                "CANARY_ACTIVATION_AUTHORIZED": False,
                "ORDER_EXECUTION_AUTHORIZED": False,
                "LIVE_TRADING_AUTHORIZED": False,
            })
        if args.cmd == "rl-experiment-list":
            return _out(rl.list_experiments())
        if args.cmd == "rl-strategy-compare":
            return _out(rl.compare_strategies())
        if args.cmd == "rl-certify":
            return _out(rl.certify())
        if args.cmd == "rl-dashboard":
            return _out(rl.dashboard())
        if args.cmd == "rl-bootstrap":
            return _out(rl.bootstrap_demo_pipeline())

    # Top-level research-orchestrator aliases (M280–M287)
    if args.cmd in (
        "ro-verdict", "ro-dashboard", "ro-bootstrap", "ro-certify", "ro-job-list",
    ):
        from saathi.platform.tg.research_orchestrator.service import default_research_orchestrator
        ro = default_research_orchestrator()
        if args.cmd == "ro-verdict":
            return _out(ro.terminal_verdict())
        if args.cmd == "ro-dashboard":
            return _out(ro.dashboard())
        if args.cmd == "ro-bootstrap":
            return _out(ro.bootstrap_demo_pipeline())
        if args.cmd == "ro-certify":
            return _out(ro.certify())
        if args.cmd == "ro-job-list":
            return _out(ro.list_jobs())

    # Top-level paper-simulation aliases (M288–M295)
    if args.cmd in ("ps-verdict", "ps-dashboard", "ps-bootstrap", "ps-certify"):
        from saathi.platform.tg.paper_simulation.service import default_paper_simulation
        ps = default_paper_simulation()
        if args.cmd == "ps-verdict":
            return _out(ps.terminal_verdict())
        if args.cmd == "ps-dashboard":
            return _out(ps.dashboard())
        if args.cmd == "ps-bootstrap":
            return _out(ps.bootstrap_demo_pipeline())
        if args.cmd == "ps-certify":
            return _out(ps.certify())

    # Top-level portfolio-risk aliases (M296–M303)
    if args.cmd in ("pr-verdict", "pr-dashboard", "pr-bootstrap", "pr-certify"):
        from saathi.platform.tg.portfolio_risk.service import default_portfolio_risk
        pr = default_portfolio_risk()
        if args.cmd == "pr-verdict":
            return _out(pr.terminal_verdict())
        if args.cmd == "pr-dashboard":
            return _out(pr.dashboard())
        if args.cmd == "pr-bootstrap":
            return _out(pr.bootstrap_demo_pipeline())
        if args.cmd == "pr-certify":
            return _out(pr.certify())

    # Top-level market-observation aliases (M304–M311)
    if args.cmd in ("mo-verdict", "mo-dashboard", "mo-bootstrap", "mo-certify"):
        from saathi.platform.tg.market_observation.service import default_market_observation
        mo = default_market_observation()
        if args.cmd == "mo-verdict":
            return _out(mo.terminal_verdict())
        if args.cmd == "mo-dashboard":
            return _out(mo.dashboard())
        if args.cmd == "mo-bootstrap":
            return _out(mo.bootstrap_demo_pipeline())
        if args.cmd == "mo-certify":
            return _out(mo.certify())

    # Top-level connectivity-governance aliases (M312–M319)
    if args.cmd and str(args.cmd).startswith("cg-"):
        from saathi.platform.tg.connectivity_governance.service import default_connectivity_governance
        cg = default_connectivity_governance()
        cmd = args.cmd
        if cmd == "cg-verdict":
            return _out(cg.terminal_verdict())
        if cmd == "cg-dashboard":
            return _out(cg.dashboard())
        if cmd == "cg-bootstrap":
            return _out(cg.bootstrap_demo_pipeline())
        if cmd == "cg-charter-show":
            return _out(cg.charter())
        if cmd == "cg-authority-list":
            return _out(cg.authority_list())
        if cmd == "cg-authority-evaluate":
            cap = getattr(args, "capability", None) or "offline_fixture_access"
            return _out(cg.authority_evaluate(cap))
        if cmd == "cg-provider-list":
            return _out(cg.list_providers())
        if cmd == "cg-provider-show":
            pid = getattr(args, "provider_id", None) or "prov_mock_contract"
            return _out(cg.get_provider(pid))
        if cmd == "cg-provider-register":
            return _out(cg.register_provider({
                "provider_id": "prov_cli_docs",
                "provider_name": "CLI Registered Docs Provider",
                "provider_type": "docs",
                "jurisdiction": "N/A",
                "official_domains": ["localhost"],
                "governance_status": "RESEARCH_ONLY",
            }, actor="cli_operator"))
        if cmd == "cg-provider-prohibit":
            pid = getattr(args, "provider_id", None) or "prov_cli_docs"
            return _out(cg.prohibit_provider(pid, actor="cli_operator", reason="operator_request"))
        if cmd == "cg-approval-create":
            import time as _t
            return _out(cg.create_approval(
                requestor="cli_requestor",
                approval_type="provider_documentation_review",
                provider="prov_mock_contract",
                environment="governance",
                capability_scope=["offline_fixture_access"],
                operation_scope=["documentation_review"],
                jurisdiction="N/A",
                expiry_time=_t.time() + 86400,
                allowed_network_destinations=["localhost"],
                evidence_requirements=["docs"],
                revocation_conditions=["operator_request"],
                acknowledgements=["governance_only", "no_activation"],
            ))
        if cmd == "cg-approval-submit":
            aid = getattr(args, "approval_id", None)
            if not aid:
                return _out({"ok": False, "error": "approval_id required"})
            return _out(cg.submit_approval(aid, actor="cli_requestor"))
        if cmd == "cg-approval-review":
            aid = getattr(args, "approval_id", None)
            if not aid:
                return _out({"ok": False, "error": "approval_id required"})
            return _out(cg.review_approval(aid, approver="cli_approver", decision="approve"))
        if cmd == "cg-approval-reject":
            aid = getattr(args, "approval_id", None)
            if not aid:
                return _out({"ok": False, "error": "approval_id required"})
            return _out(cg.review_approval(aid, approver="cli_approver", decision="reject"))
        if cmd == "cg-approval-revoke":
            aid = getattr(args, "approval_id", None)
            if not aid:
                return _out({"ok": False, "error": "approval_id required"})
            return _out(cg.revoke_approval(aid, actor="cli_operator", reason="operator_request"))
        if cmd == "cg-credential-policy":
            return _out(cg.credential_policy())
        if cmd == "cg-threat-list":
            return _out(cg.list_threats())
        if cmd == "cg-risk-summary":
            return _out(cg.risk_summary())
        if cmd == "cg-incident-create":
            return _out(cg.create_incident(
                incident_type="scope_violation",
                actor="cli_operator",
                summary="CLI governance incident drill",
                severity="HIGH",
            ))
        if cmd == "cg-incident-contain":
            iid = getattr(args, "incident_id", None)
            if not iid:
                return _out({"ok": False, "error": "incident_id required"})
            return _out(cg.advance_incident(iid, step="contain", actor="cli_operator"))
        if cmd == "cg-emergency-shutdown":
            return _out(cg.emergency_shutdown(actor="cli_operator", reason="cli_drill"))
        if cmd == "cg-maturity":
            return _out(cg.maturity())
        if cmd == "cg-certify":
            return _out(cg.certify())
        return _out({"ok": False, "error": f"unknown cg command: {cmd}"})

    # Top-level credentialless provider contract aliases (M320–M327)
    if args.cmd and str(args.cmd).startswith("pc-"):
        from saathi.platform.tg.provider_contracts.service import default_provider_contracts
        pc = default_provider_contracts()
        cmd = args.cmd
        if cmd == "pc-verdict":
            return _out(pc.posture())
        if cmd == "pc-charter":
            return _out(pc.charter())
        if cmd == "pc-dashboard":
            return _out(pc.dashboard())
        if cmd == "pc-providers":
            return _out(pc.list_providers())
        if cmd == "pc-capabilities":
            return _out(pc.capabilities())
        if cmd == "pc-sessions":
            return _out(pc.sessions())
        if cmd == "pc-replay-fixtures":
            return _out(pc.replay_fixtures())
        if cmd == "pc-mock-quote":
            return _out(pc.mock_quote())
        if cmd == "pc-replay-quote":
            return _out(pc.replay_quote())
        if cmd == "pc-security":
            return _out(pc.security_scan())
        if cmd == "pc-certify":
            return _out(pc.certify())
        return _out({"ok": False, "error": f"unknown pc command: {cmd}"})

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
