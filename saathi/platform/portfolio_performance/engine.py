"""PortfolioPerformanceEngine — historical NAV, returns, drawdown, contribution.

Read/derived only. Zero ledger/risk/proposal/order mutation authority.
"""
from __future__ import annotations

import hashlib
import time as _time
import uuid
from decimal import Decimal
from typing import Any, Callable

from saathi.platform.fund_ledger.money import D, q_money
from saathi.platform.portfolio_performance.contribution import position_contributions
from saathi.platform.portfolio_performance.policy import DEFAULT_POLICY, PerformancePolicy
from saathi.platform.portfolio_performance.returns import (
    period_return_with_flows,
    realized_volatility,
    sharpe_ratio,
    simple_return,
)
from saathi.platform.portfolio_performance.store import PerformanceStore
from saathi.platform.portfolio_risk_engine.drawdown import compute_drawdown


PERIODS = {
    "1D": 86400.0,
    "1W": 7 * 86400.0,
    "1M": 30 * 86400.0,
    "3M": 90 * 86400.0,
    "YTD": None,  # special
    "SINCE_INCEPTION": None,
}


class PortfolioPerformanceEngine:
    def __init__(
        self,
        *,
        store: PerformanceStore | None = None,
        policy: PerformancePolicy | None = None,
        get_ledger_state: Callable[[str], dict] | None = None,
        get_recon: Callable[[str], dict] | None = None,
        get_events: Callable[[str], list] | None = None,
        list_proposals: Callable[[str], list] | None = None,
    ):
        self.store = store or PerformanceStore()
        self.policy = policy or DEFAULT_POLICY
        self._get_state = get_ledger_state
        self._get_recon = get_recon
        self._get_events = get_events
        self._list_proposals = list_proposals

    def bind_ledger(
        self,
        get_ledger_state: Callable[[str], dict],
        get_recon: Callable[[str], dict] | None = None,
        get_events: Callable[[str], list] | None = None,
    ) -> "PortfolioPerformanceEngine":
        self._get_state = get_ledger_state
        self._get_recon = get_recon
        self._get_events = get_events
        return self

    # ── observation ──────────────────────────────────────────────────────
    def record_observation_from_state(
        self,
        fund_id: str,
        state: dict | None = None,
        *,
        external_flow: Decimal | str | None = None,
        ts: float | None = None,
        recon: dict | None = None,
    ) -> dict:
        """Record a valuation observation from canonical ledger state.

        Idempotent on state_hash. Does not mutate ledger.
        """
        st = state or (self._get_state(fund_id) if self._get_state else None)
        if not st:
            return {"ok": False, "status": "DATA_INSUFFICIENT", "reason": "no_ledger_state"}

        recon_st = recon
        if recon_st is None and self._get_recon:
            try:
                recon_st = self._get_recon(fund_id)
            except Exception:
                recon_st = None
        if recon_st and (
            recon_st.get("ok") is False
            or recon_st.get("portfolio_status") == "RECONCILIATION_REQUIRED"
        ):
            # Still allow recording with status flag for history, but mark incomplete trust
            trust = "RECONCILIATION_REQUIRED"
        else:
            trust = "OK"

        t = float(ts if ts is not None else st.get("ts") or _time.time())
        positions = list(st.get("positions") or [])
        stale = []
        for p in positions:
            if p.get("mark_stale") or (p.get("mark") or {}).get("stale"):
                stale.append(p.get("security_id") or p.get("symbol"))
        mark_stale = bool(stale) or bool(st.get("mark_stale"))

        state_hash = st.get("state_hash") or self._hash_state(st)
        obs = {
            "observation_id": f"pobs_{uuid.uuid4().hex[:16]}",
            "fund_id": fund_id,
            "ts": t,
            "state_hash": state_hash,
            "event_count": int(st.get("event_count") or 0),
            "nav": str(q_money(st.get("nav") or st.get("paper_nav") or "0")),
            "cash": str(q_money(st.get("cash") or "0")),
            "market_value": str(q_money(st.get("positions_value") or "0")),
            "realized_pnl": str(q_money(st.get("realized_pnl") or "0")),
            "unrealized_pnl": str(q_money(st.get("unrealized_pnl") or "0")),
            "total_fees": str(q_money(st.get("total_fees") or "0")),
            "external_flow": str(q_money(external_flow or "0")),
            "mark_stale": mark_stale,
            "stale_securities": stale,
            "positions": positions,
            "trust": trust,
            "freshness": "STALE" if mark_stale else "FRESH",
            "valuation_status": "INCOMPLETE_VALUATION" if mark_stale else "COMPLETE",
            "source": "canonical_fund_ledger",
            "mode": "PAPER",
            "engine_version": "portfolio-performance/1.0.0",
        }
        result = self.store.upsert_observation(obs)
        result["observation"] = obs
        result["trust"] = trust
        return result

    def rebuild_from_events(self, fund_id: str, events: list | None = None) -> dict:
        """Replay ledger events to reconstruct observations at each event (deterministic).

        Does not mutate ledger. Uses bound get_events or provided list.
        External flows tagged on DEPOSIT/WITHDRAWAL_SIM events.
        """
        from saathi.platform.fund_ledger.reducer import reduce_events
        from saathi.platform.fund_ledger.models import LedgerEvent, EventType

        raw = events if events is not None else (self._get_events(fund_id) if self._get_events else [])
        if not raw:
            return {"ok": False, "status": "DATA_INSUFFICIENT", "recorded": 0}

        evs = []
        for e in raw:
            if isinstance(e, LedgerEvent):
                evs.append(e)
            elif isinstance(e, dict):
                try:
                    evs.append(LedgerEvent.from_record(e))
                except Exception:
                    evs.append(self._event_from_dict(e))
            else:
                continue

        recorded = 0
        for i in range(len(evs)):
            subset = evs[: i + 1]
            try:
                state = reduce_events(subset, fund_id=fund_id)
                pub = state.to_public() if hasattr(state, "to_public") else dict(state)
            except Exception:
                continue
            et = subset[-1].event_type
            etv = et.value if hasattr(et, "value") else str(et)
            flow = Decimal("0")
            if etv == "DEPOSIT":
                flow = D(subset[-1].cash_delta)
            elif etv == "WITHDRAWAL_SIM":
                flow = D(subset[-1].cash_delta)
                if flow > 0:
                    flow = -flow
            r = self.record_observation_from_state(
                fund_id,
                pub if isinstance(pub, dict) else {},
                external_flow=flow,
                ts=float(subset[-1].ts),
            )
            if r.get("inserted"):
                recorded += 1
        return {"ok": True, "recorded": recorded, "events": len(evs)}

    def _event_from_dict(self, d: dict):
        from saathi.platform.fund_ledger.models import LedgerEvent, EventType

        return LedgerEvent(
            event_id=d.get("event_id") or f"tmp_{uuid.uuid4().hex[:8]}",
            fund_id=d["fund_id"],
            event_type=EventType(d["event_type"]) if not isinstance(d.get("event_type"), EventType) else d["event_type"],
            ts=float(d.get("ts") or 0),
            actor=d.get("actor") or "system",
            source=d.get("source") or "paper",
            security_id=d.get("security_id") or "",
            symbol=d.get("symbol") or "",
            side=d.get("side") or "",
            quantity=D(d.get("quantity") or "0"),
            price=D(d.get("price") or "0"),
            fee=D(d.get("fee") or "0"),
            cash_delta=D(d.get("cash_delta") or "0"),
            currency=d.get("currency") or "USD",
            fill_ref=d.get("fill_ref") or "",
            order_ref=d.get("order_ref") or "",
            reason=d.get("reason") or "",
            reverses_event_id=d.get("reverses_event_id") or "",
            idempotency_key=d.get("idempotency_key") or d.get("event_id") or uuid.uuid4().hex,
        )

    # ── queries ──────────────────────────────────────────────────────────
    def get_nav_history(self, fund_id: str, *, since: float | None = None, until: float | None = None) -> dict:
        obs = self.store.list_observations(fund_id, since=since, until=until)
        series = [
            {
                "timestamp": o["ts"],
                "value": o["nav"],
                "provenance": "LIVE" if o.get("source") == "canonical_fund_ledger" else "DERIVED",
                "freshness": o.get("freshness") or "FRESH",
                "observation_id": o["observation_id"],
            }
            for o in obs
        ]
        return {
            "fund_id": fund_id,
            "series": series,
            "n": len(series),
            "status": "OK" if series else "DATA_INSUFFICIENT",
            "mode": "PAPER",
        }

    def get_pnl_history(self, fund_id: str, *, since: float | None = None, until: float | None = None) -> dict:
        obs = self.store.list_observations(fund_id, since=since, until=until)
        series = [
            {
                "timestamp": o["ts"],
                "realized_pnl": o["realized_pnl"],
                "unrealized_pnl": o["unrealized_pnl"],
                "total_pnl": str(q_money(D(o["realized_pnl"]) + D(o["unrealized_pnl"]))),
                "total_fees": o.get("total_fees") or "0",
                "provenance": "LIVE",
            }
            for o in obs
        ]
        return {"fund_id": fund_id, "series": series, "n": len(series), "status": "OK" if series else "DATA_INSUFFICIENT"}

    def get_drawdown_history(self, fund_id: str) -> dict:
        """Historical drawdown series. RiskEngine remains limit authority — this is history only."""
        obs = self.store.list_observations(fund_id)
        nav_series = [(o["ts"], o["nav"]) for o in obs]
        summary = compute_drawdown(nav_series)
        # per-point drawdown path
        peak = Decimal("0")
        path = []
        peak_ts = None
        under_water_start = None
        for ts, nav in nav_series:
            n = D(nav)
            if n > peak:
                peak = n
                peak_ts = ts
                under_water_start = None
            dd = (peak - n) / peak if peak > 0 else Decimal("0")
            if dd < 0:
                dd = Decimal("0")  # invariant: drawdown never > 0% means never negative? 
                # Spec: "drawdown never > 0%" — drawdown is expressed as non-negative fraction of loss
                # "never > 0%" would mean drawdown is always 0 which is wrong.
                # Interpret: drawdown value is always >= 0 (never positive return as drawdown)
            if dd > 0 and under_water_start is None:
                under_water_start = ts
            path.append(
                {
                    "timestamp": ts,
                    "value": str(q_money(dd)),
                    "peak_nav": str(q_money(peak)),
                    "nav": str(q_money(n)),
                    "provenance": "DERIVED",
                }
            )
        duration = None
        if under_water_start is not None and path:
            duration = path[-1]["timestamp"] - under_water_start
        return {
            "fund_id": fund_id,
            "summary": summary,
            "series": path,
            "drawdown_duration_seconds": duration,
            "status": "OK" if path else "DATA_INSUFFICIENT",
            "authority_note": "history only — PortfolioRiskEngine owns hard limits",
            "mode": "PAPER",
        }

    def get_return_series(self, fund_id: str) -> dict:
        obs = self.store.list_observations(fund_id)
        if len(obs) < 2:
            return {"status": "DATA_INSUFFICIENT", "series": [], "n": len(obs)}
        series = []
        for a, b in zip(obs, obs[1:]):
            pr = period_return_with_flows([a, b])
            series.append(
                {
                    "timestamp": b["ts"],
                    "value": pr.get("return_pct"),
                    "methodology": pr.get("methodology"),
                    "provenance": "DERIVED",
                }
            )
        return {"fund_id": fund_id, "series": series, "n": len(series), "status": "OK"}

    def get_position_contribution(self, fund_id: str, *, period: str = "SINCE_INCEPTION") -> dict:
        window = self._window_obs(fund_id, period)
        if window.get("status") != "OK":
            return window
        obs = window["observations"]
        if len(obs) < 2:
            return {"status": "DATA_INSUFFICIENT", "reason": "need_two_observations"}
        contrib = position_contributions(obs[0], obs[-1])
        # reconcile check
        tol = self.policy.contribution_tolerance
        gap = abs(D(contrib["aggregate_contribution"]) - D(contrib["portfolio_pnl_change"]))
        contrib["reconcile_ok"] = gap <= tol
        contrib["reconcile_gap"] = str(q_money(gap))
        contrib["period"] = period
        contrib["status"] = "OK"
        contrib["mode"] = "PAPER"
        return contrib

    def get_period_summary(self, fund_id: str, period: str = "SINCE_INCEPTION") -> dict:
        window = self._window_obs(fund_id, period)
        if window.get("status") != "OK":
            return {
                "period": period,
                "status": window.get("status") or "DATA_INSUFFICIENT",
                "reason": window.get("reason"),
            }
        obs = window["observations"]
        ret = period_return_with_flows(obs)
        start, end = obs[0], obs[-1]
        dd = compute_drawdown([(o["ts"], o["nav"]) for o in obs])
        # incomplete valuation?
        incomplete = any(o.get("valuation_status") == "INCOMPLETE_VALUATION" or o.get("mark_stale") for o in obs)
        trust = "OK"
        if any(o.get("trust") == "RECONCILIATION_REQUIRED" for o in obs):
            trust = "RECONCILIATION_REQUIRED"
        elif incomplete:
            trust = "INCOMPLETE_VALUATION"

        return {
            "period": period,
            "status": "OK" if ret.get("status") == "OK" else ret.get("status"),
            "trust": trust,
            "start_ts": start["ts"],
            "end_ts": end["ts"],
            "start_nav": start["nav"],
            "end_nav": end["nav"],
            "return": ret,
            "realized_pnl_start": start["realized_pnl"],
            "realized_pnl_end": end["realized_pnl"],
            "unrealized_pnl_start": start["unrealized_pnl"],
            "unrealized_pnl_end": end["unrealized_pnl"],
            "realized_pnl_change": str(q_money(D(end["realized_pnl"]) - D(start["realized_pnl"]))),
            "unrealized_pnl_change": str(q_money(D(end["unrealized_pnl"]) - D(start["unrealized_pnl"]))),
            "total_pnl_change": str(
                q_money(
                    (D(end["realized_pnl"]) + D(end["unrealized_pnl"]))
                    - (D(start["realized_pnl"]) + D(start["unrealized_pnl"]))
                )
            ),
            "fees_end": end.get("total_fees") or "0",
            "fee_change": str(q_money(D(end.get("total_fees") or 0) - D(start.get("total_fees") or 0))),
            "drawdown": dd,
            "observations": len(obs),
            "mode": "PAPER",
            "currency_boundary": self.policy.currency_boundary,
        }

    def get_win_loss(self, fund_id: str) -> dict:
        """Win/loss from closed lots if present on latest observation / events."""
        # Prefer events SELL fills with realized
        events = self._get_events(fund_id) if self._get_events else []
        wins = losses = 0
        gain_sum = Decimal("0")
        loss_sum = Decimal("0")
        unit = self.policy.win_loss_unit
        for e in events or []:
            et = e.get("event_type") if isinstance(e, dict) else getattr(e, "event_type", None)
            etv = et.value if hasattr(et, "value") else str(et or "")
            if etv != "SELL_FILL":
                continue
            # realized in payload if present
            payload = e.get("payload") if isinstance(e, dict) else getattr(e, "payload", {}) or {}
            if isinstance(payload, str):
                import json

                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = {}
            realized = D(payload.get("realized_pnl") or "0")
            if realized > 0:
                wins += 1
                gain_sum += realized
            elif realized < 0:
                losses += 1
                loss_sum += abs(realized)
        n = wins + losses
        if n == 0:
            return {
                "status": "DATA_INSUFFICIENT",
                "unit": unit,
                "wins": 0,
                "losses": 0,
                "win_rate": None,
                "note": "no closed-lot realized outcomes recorded on SELL fills",
            }
        win_rate = Decimal(wins) / Decimal(n)
        avg_gain = gain_sum / Decimal(wins) if wins else Decimal("0")
        avg_loss = loss_sum / Decimal(losses) if losses else Decimal("0")
        profit_factor = (gain_sum / loss_sum) if loss_sum > 0 else None
        return {
            "status": "OK",
            "unit": unit,
            "wins": wins,
            "losses": losses,
            "win_rate": str(q_money(win_rate)),
            "average_gain": str(q_money(avg_gain)),
            "average_loss": str(q_money(avg_loss)),
            "profit_factor": str(q_money(profit_factor)) if profit_factor is not None else None,
            "mode": "PAPER",
        }

    def get_decision_history(self, fund_id: str) -> dict:
        """Read-only timeline: proposals, fills (via events), performance associations.

        Wording: ASSOCIATED_WITH / FOLLOWED_BY — never causal proof.
        """
        links = list(self.store.list_decision_links(fund_id))
        # auto-associate proposals if callback provided
        if self._list_proposals:
            try:
                for p in self._list_proposals(fund_id) or []:
                    links.append(
                        {
                            "ts": p.get("created_at") or 0,
                            "kind": "proposal",
                            "ref_id": p.get("id") or p.get("proposal_id") or "",
                            "note": p.get("status") or "",
                            "association": "ASSOCIATED_WITH",
                            "payload": {
                                "status": p.get("status"),
                                "method": p.get("method"),
                                "reason_codes": p.get("reason_codes"),
                            },
                        }
                    )
            except Exception:
                pass
        if self._get_events:
            try:
                for e in self._get_events(fund_id) or []:
                    et = e.get("event_type") if isinstance(e, dict) else str(getattr(e, "event_type", ""))
                    etv = et if isinstance(et, str) else getattr(et, "value", str(et))
                    if etv in ("BUY_FILL", "SELL_FILL", "DEPOSIT", "FEE"):
                        links.append(
                            {
                                "ts": e.get("ts") if isinstance(e, dict) else getattr(e, "ts", 0),
                                "kind": etv.lower(),
                                "ref_id": (e.get("event_id") if isinstance(e, dict) else getattr(e, "event_id", "")),
                                "note": etv,
                                "association": "FOLLOWED_BY",
                                "payload": {},
                            }
                        )
            except Exception:
                pass
        links.sort(key=lambda x: float(x.get("ts") or 0))
        # attach subsequent performance marker
        obs = self.store.list_observations(fund_id)
        for i, link in enumerate(links):
            ts = float(link.get("ts") or 0)
            later = [o for o in obs if o["ts"] >= ts]
            if later:
                link["subsequent_nav"] = later[0]["nav"]
                link["association"] = link.get("association") or "FOLLOWED_BY"
            else:
                link["subsequent_nav"] = None
        return {
            "fund_id": fund_id,
            "events": links,
            "status": "OK",
            "causal_claim": False,
            "wording": "ASSOCIATED_WITH / FOLLOWED_BY only",
            "mode": "PAPER",
        }

    def get_performance_snapshot(self, fund_id: str, period: str = "SINCE_INCEPTION") -> dict:
        """UI-ready performance contract."""
        # live recon gate
        recon_status = "OK"
        if self._get_recon:
            try:
                r = self._get_recon(fund_id)
                if r and (r.get("ok") is False or r.get("portfolio_status") == "RECONCILIATION_REQUIRED"):
                    recon_status = "RECONCILIATION_REQUIRED"
            except Exception:
                pass

        summary = self.get_period_summary(fund_id, period)
        nav_hist = self.get_nav_history(fund_id)
        dd_hist = self.get_drawdown_history(fund_id)
        pnl_hist = self.get_pnl_history(fund_id)
        contrib = self.get_position_contribution(fund_id, period=period) if summary.get("status") == "OK" else {
            "status": "DATA_INSUFFICIENT",
            "top_contributors": [],
            "bottom_contributors": [],
        }
        ret_series = self.get_return_series(fund_id)
        rets = []
        for s in ret_series.get("series") or []:
            if s.get("value") is not None:
                rets.append(D(s["value"]))
        vol = realized_volatility(
            rets,
            annualization=self.policy.annualization_factor,
            min_n=self.policy.min_observations_for_volatility,
        )
        sharpe = sharpe_ratio(
            rets,
            risk_free_per_period=Decimal("0"),
            annualization=self.policy.annualization_factor,
            min_n=self.policy.min_observations_for_sharpe,
            assumption=self.policy.risk_free_assumption,
        )
        win_loss = self.get_win_loss(fund_id)

        trust = summary.get("trust") or "OK"
        if recon_status == "RECONCILIATION_REQUIRED":
            trust = "RECONCILIATION_REQUIRED"

        # latest NAV
        obs = self.store.list_observations(fund_id)
        latest = obs[-1] if obs else None

        return {
            "performance": {
                "period": period,
                "nav": latest["nav"] if latest else None,
                "return_pct": (summary.get("return") or {}).get("return_pct"),
                "return_methodology": (summary.get("return") or {}).get("methodology"),
                "realized_pnl": latest["realized_pnl"] if latest else None,
                "unrealized_pnl": latest["unrealized_pnl"] if latest else None,
                "total_pnl": (
                    str(q_money(D(latest["realized_pnl"]) + D(latest["unrealized_pnl"]))) if latest else None
                ),
                "max_drawdown": (dd_hist.get("summary") or {}).get("max_drawdown"),
                "current_drawdown": (dd_hist.get("summary") or {}).get("current_drawdown"),
                "volatility": vol.get("volatility_annualized") or vol.get("volatility"),
                "volatility_status": vol.get("status"),
                "sharpe": sharpe.get("sharpe"),
                "sharpe_status": sharpe.get("status"),
                "sharpe_assumption": sharpe.get("risk_free_assumption"),
                "sortino": None,
                "sortino_status": "DEFER",
                "benchmark_return": None,
                "benchmark_status": "BENCHMARK_UNAVAILABLE",
                "excess_return": None,
                "alpha": None,
                "beta": None,
                "alpha_beta_status": "DEFER",
                "top_contributors": contrib.get("top_contributors") or [],
                "bottom_contributors": contrib.get("bottom_contributors") or [],
                "contribution_kind": "POSITION_CONTRIBUTION",
                "win_loss": win_loss,
                "history": {
                    "nav": nav_hist.get("series") or [],
                    "drawdown": dd_hist.get("series") or [],
                    "pnl": pnl_hist.get("series") or [],
                    "returns": ret_series.get("series") or [],
                },
                "period_summary": summary,
                "provenance": "DERIVED" if latest else "UNAVAILABLE",
                "freshness": latest.get("freshness") if latest else "DATA_INSUFFICIENT",
                "trust": trust,
                "reconciliation": recon_status,
                "currency_boundary": self.policy.currency_boundary,
                "mode": "PAPER",
                "live_execution": "UNAVAILABLE",
                "authorizes_execution": False,
                "engine_version": "portfolio-performance/1.0.0",
                "source": "portfolio_performance_engine",
            }
        }

    def command_performance_contract(self, fund_id: str, period: str = "SINCE_INCEPTION") -> dict:
        """Thin Command/Investments-mode read contract."""
        snap = self.get_performance_snapshot(fund_id, period=period)
        perf = snap["performance"]
        return {
            "paper_performance": {
                "label": "PAPER PERFORMANCE",
                "mode": "PAPER",
                "live_execution": "UNAVAILABLE",
                "period": perf["period"],
                "nav": perf["nav"],
                "return_pct": perf["return_pct"],
                "return_methodology": perf["return_methodology"],
                "realized_pnl": perf["realized_pnl"],
                "unrealized_pnl": perf["unrealized_pnl"],
                "total_pnl": perf["total_pnl"],
                "max_drawdown": perf["max_drawdown"],
                "current_drawdown": perf["current_drawdown"],
                "volatility": perf["volatility"],
                "volatility_status": perf["volatility_status"],
                "benchmark_status": perf["benchmark_status"],
                "excess_return": None,
                "top_contributors": perf["top_contributors"][:3],
                "bottom_contributors": perf["bottom_contributors"][:3],
                "history_nav": perf["history"]["nav"][-60:],
                "history_drawdown": perf["history"]["drawdown"][-60:],
                "provenance": perf["provenance"],
                "freshness": perf["freshness"],
                "trust": perf["trust"],
                "reconciliation": perf["reconciliation"],
                "source": "portfolio_performance_engine",
            }
        }

    def link_decision(self, fund_id: str, kind: str, ref_id: str = "", note: str = "", **payload) -> None:
        self.store.add_decision_link(fund_id, kind, ref_id=ref_id, note=note, payload=payload)

    # ── internals ────────────────────────────────────────────────────────
    def _window_obs(self, fund_id: str, period: str) -> dict:
        obs = self.store.list_observations(fund_id)
        if not obs:
            return {"status": "DATA_INSUFFICIENT", "reason": "no_observations", "observations": []}
        if period == "SINCE_INCEPTION" or period == "CUSTOM":
            return {"status": "OK", "observations": obs}
        now = obs[-1]["ts"]
        if period == "YTD":
            import datetime as dt

            d = dt.datetime.utcfromtimestamp(now)
            start = dt.datetime(d.year, 1, 1).timestamp()
            window = [o for o in obs if o["ts"] >= start]
        else:
            secs = PERIODS.get(period)
            if secs is None:
                return {"status": "DATA_INSUFFICIENT", "reason": f"unknown_period:{period}", "observations": []}
            start = now - secs
            window = [o for o in obs if o["ts"] >= start]
            # include last obs before window as start anchor if available
            before = [o for o in obs if o["ts"] < start]
            if before and (not window or window[0]["ts"] > start):
                window = [before[-1]] + window
        if len(window) < 2:
            return {
                "status": "DATA_INSUFFICIENT",
                "reason": f"insufficient_history_for_{period}",
                "observations": window,
            }
        return {"status": "OK", "observations": window}

    def _hash_state(self, state: dict) -> str:
        raw = f"{state.get('nav')}|{state.get('cash')}|{state.get('event_count')}|{state.get('realized_pnl')}|{state.get('unrealized_pnl')}"
        return "sh_" + hashlib.sha256(raw.encode()).hexdigest()[:16]
