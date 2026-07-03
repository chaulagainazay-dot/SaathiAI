"""Portfolio Intelligence Department (M5 Phase 4) — managing wealth as a system.

M5 shifts here from *finding* good opportunities to *managing* everything owned.
The department is a set of deterministic engines over a single source of truth,
the Portfolio Registry — no other module mutates positions.

Engines:
  1. PortfolioRegistry      — owns the truth (cash, positions, transactions)
  2. AllocationEngine       — cash / crypto / stocks / business / AI %, all USD
  3. DiversificationEngine  — sector/country/asset-class HHI, meme/AI/stable ratio
  4. PortfolioRiskEngine    — drawdown, concentration, correlation, liquidity,
                              volatility, leverage, cash runway (portfolio-level)
  5. PortfolioHealthScore   — one number from six sub-scores, shown each morning
  6. RebalancingEngine      — recommendations only, never trades

Plus:
  • PortfolioImpactSimulator — evaluate an opportunity INSIDE the portfolio
    (before vs after), not in isolation. Never mutates the registry.
  • CapitalReserveEngine     — every dollar competes across financial assets AND
    business expansion (cafeteria, AI Studio, SaathiAI feature, marketing).

Deterministic (AP-17); optional correlation matrix / burn / goal injected (AP-12).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from enum import Enum

from saathi.investment import AssetClass


# ── 1. Portfolio Registry (owns the truth) ──────────────────────────────────
@dataclass
class Position:
    symbol: str
    asset_class: AssetClass
    usd_value: float
    sector: str = "unclassified"
    country: str = "global"
    cost_basis_usd: float = 0.0
    volatility: float = 0.3          # 0..1 annualized proxy (higher = riskier)
    liquidity: float = 0.8           # 0..1 (1 = instantly sellable)
    stablecoin: bool = False
    meme: bool = False
    small_cap: bool = False
    ai: bool = False


@dataclass
class PortfolioRegistry:
    cash_usd: float = 0.0
    emergency_fund_usd: float = 0.0   # portion of cash reserved, not investable
    borrowed_usd: float = 0.0         # for leverage
    positions: list[Position] = field(default_factory=list)
    transactions: list[dict] = field(default_factory=list)

    # only these methods change holdings
    def deposit_cash(self, usd: float) -> None:
        self.cash_usd += usd
        self.transactions.append({"type": "deposit", "usd": usd})

    def add_position(self, pos: Position, *, fund_from_cash: bool = True) -> None:
        if fund_from_cash:
            self.cash_usd -= pos.usd_value
        self.positions.append(pos)
        self.transactions.append({"type": "buy", "symbol": pos.symbol, "usd": pos.usd_value})

    @property
    def invested_usd(self) -> float:
        return sum(p.usd_value for p in self.positions)

    @property
    def total_value_usd(self) -> float:
        return self.cash_usd + self.invested_usd

    def clone(self) -> "PortfolioRegistry":
        return copy.deepcopy(self)


def _weights(positions: list[Position]) -> list[tuple[Position, float]]:
    total = sum(p.usd_value for p in positions) or 1.0
    return [(p, p.usd_value / total) for p in positions]


def _hhi(shares: list[float]) -> float:
    """Herfindahl-Hirschman index, 0..1. Higher = more concentrated."""
    return round(sum(s * s for s in shares), 4)


# ── 2. Allocation Engine ────────────────────────────────────────────────────
@dataclass
class AllocationBreakdown:
    total_usd: float
    cash_pct: float
    emergency_pct: float
    by_class: dict[str, float]        # asset_class value → % of total

    def render(self) -> str:
        parts = [f"cash {self.cash_pct:.0%}"] + \
                [f"{k} {v:.0%}" for k, v in sorted(self.by_class.items(), key=lambda x: -x[1])]
        return "Allocation: " + ", ".join(parts)


class AllocationEngine:
    def allocate(self, reg: PortfolioRegistry) -> AllocationBreakdown:
        total = reg.total_value_usd or 1.0
        by_class: dict[str, float] = {}
        for p in reg.positions:
            by_class[p.asset_class.value] = by_class.get(p.asset_class.value, 0.0) + p.usd_value
        by_class = {k: round(v / total, 4) for k, v in by_class.items()}
        return AllocationBreakdown(
            total_usd=round(total, 2),
            cash_pct=round(reg.cash_usd / total, 4),
            emergency_pct=round(reg.emergency_fund_usd / total, 4),
            by_class=by_class)


# ── 3. Diversification Engine ───────────────────────────────────────────────
@dataclass
class DiversificationReport:
    sector_concentration: float       # HHI 0..1
    asset_class_concentration: float
    country_concentration: float
    stablecoin_ratio: float
    meme_exposure: float
    small_cap_exposure: float
    ai_exposure: float
    diversification_score: float      # 0..100 (higher = better diversified)


class DiversificationEngine:
    def assess(self, reg: PortfolioRegistry) -> DiversificationReport:
        w = _weights(reg.positions)
        if not w:
            return DiversificationReport(0, 0, 0, 0, 0, 0, 0, 100.0)

        def group_hhi(key) -> float:
            g: dict[str, float] = {}
            for p, share in w:
                g[key(p)] = g.get(key(p), 0.0) + share
            return _hhi(list(g.values()))

        sector_hhi = group_hhi(lambda p: p.sector)
        class_hhi = group_hhi(lambda p: p.asset_class.value)
        country_hhi = group_hhi(lambda p: p.country)
        stable = round(sum(s for p, s in w if p.stablecoin), 4)
        meme = round(sum(s for p, s in w if p.meme), 4)
        small = round(sum(s for p, s in w if p.small_cap), 4)
        ai = round(sum(s for p, s in w if p.ai), 4)
        # score: reward low concentration across sector & class
        score = round(100 * (1 - (sector_hhi + class_hhi) / 2), 1)
        return DiversificationReport(sector_hhi, class_hhi, country_hhi,
                                     stable, meme, small, ai, max(0.0, score))


# ── 4. Portfolio Risk Engine v2 (portfolio-level, not opportunity-level) ────
@dataclass
class PortfolioRiskReport:
    weighted_volatility: float
    max_drawdown_est: float           # 0..1
    concentration: float              # largest single position weight
    correlation: float                # avg pairwise, 0..1
    liquidity: float                  # weighted, 0..1 (higher = more liquid)
    leverage: float                   # borrowed / equity
    cash_runway_months: float
    risk_score: float                 # 0..100 (higher = safer)


class PortfolioRiskEngine:
    def assess(self, reg: PortfolioRegistry, *,
               monthly_burn_usd: float = 0.0,
               correlation_matrix: dict[tuple[str, str], float] | None = None
               ) -> PortfolioRiskReport:
        w = _weights(reg.positions)
        if not w:
            runway = float("inf") if monthly_burn_usd == 0 else reg.cash_usd / monthly_burn_usd
            return PortfolioRiskReport(0, 0, 0, 0, 1.0, 0, runway, 100.0)

        wvol = round(sum(share * p.volatility for p, share in w), 4)
        max_dd = round(min(0.95, wvol * 2.5), 4)
        concentration = round(max(share for _, share in w), 4)
        wliq = round(sum(share * p.liquidity for p, share in w), 4)
        equity = reg.total_value_usd or 1.0
        leverage = round(reg.borrowed_usd / equity, 4)

        # correlation: explicit matrix if given, else same-sector proxy
        corr = self._avg_correlation(w, correlation_matrix)
        runway = float("inf") if monthly_burn_usd == 0 else round(reg.cash_usd / monthly_burn_usd, 1)

        # safety score: penalize drawdown, concentration, correlation, leverage;
        # reward liquidity.
        risk_score = round(max(0.0, min(100.0, 100
                        - max_dd * 40 - concentration * 25 - corr * 15
                        - leverage * 20 + (wliq - 0.5) * 20)), 1)
        return PortfolioRiskReport(wvol, max_dd, concentration, corr, wliq,
                                   leverage, runway, risk_score)

    @staticmethod
    def _avg_correlation(w, matrix) -> float:
        pairs, total = 0, 0.0
        for i in range(len(w)):
            for j in range(i + 1, len(w)):
                pi, pj = w[i][0], w[j][0]
                if matrix is not None:
                    rho = matrix.get((pi.symbol, pj.symbol),
                                     matrix.get((pj.symbol, pi.symbol), 0.2))
                else:
                    rho = 0.7 if pi.sector == pj.sector else 0.2
                weight = w[i][1] * w[j][1]
                total += rho * weight
                pairs += 1
        # normalize by summed pair weights so it stays 0..1
        denom = sum(w[i][1] * w[j][1] for i in range(len(w)) for j in range(i + 1, len(w))) or 1.0
        return round(total / denom, 4) if pairs else 0.0


# ── 5. Portfolio Health Score (one number) ──────────────────────────────────
@dataclass
class HealthReport:
    overall: float
    allocation: float
    risk: float
    diversification: float
    liquidity: float
    goal_alignment: float
    performance: float

    def render(self) -> str:
        return (f"🩺 Portfolio Health {self.overall:.0f}/100 "
                f"(alloc {self.allocation:.0f} · risk {self.risk:.0f} · "
                f"divers {self.diversification:.0f} · liq {self.liquidity:.0f} · "
                f"goal {self.goal_alignment:.0f} · perf {self.performance:.0f})")


class PortfolioHealthScore:
    def compute(self, reg: PortfolioRegistry, *, target_cash_pct: float = 0.1,
                monthly_burn_usd: float = 0.0,
                correlation_matrix: dict[tuple[str, str], float] | None = None
                ) -> HealthReport:
        alloc = AllocationEngine().allocate(reg)
        divers = DiversificationEngine().assess(reg)
        risk = PortfolioRiskEngine().assess(
            reg, monthly_burn_usd=monthly_burn_usd, correlation_matrix=correlation_matrix)

        # allocation health: penalize deviation from target cash buffer
        alloc_health = round(max(0.0, 100 - abs(alloc.cash_pct - target_cash_pct) * 300), 1)
        # liquidity sub-score (0..100)
        liq = round(risk.liquidity * 100, 1)
        # goal alignment: idle over-cashing drags long-term growth
        goal = round(max(0.0, 100 - max(0.0, alloc.cash_pct - target_cash_pct * 2) * 200), 1)
        # performance vs cost basis (50 = flat)
        cost = sum(p.cost_basis_usd for p in reg.positions)
        if cost > 0:
            ret = (reg.invested_usd - cost) / cost
            perf = round(max(0.0, min(100.0, 50 + ret * 100)), 1)
        else:
            perf = 50.0

        overall = round(0.20 * alloc_health + 0.25 * risk.risk_score
                        + 0.20 * divers.diversification_score + 0.15 * liq
                        + 0.10 * goal + 0.10 * perf, 1)
        return HealthReport(overall, alloc_health, risk.risk_score,
                            divers.diversification_score, liq, goal, perf)


# ── 6. Rebalancing Engine (recommendations only, never trades) ──────────────
@dataclass
class RebalanceAction:
    action: str                       # "reduce" | "increase"
    target: str                       # asset_class value or "cash"
    delta_pct: float                  # magnitude, e.g. 0.03 = 3 percentage points
    reason: str

    def render(self) -> str:
        return f"{self.action.title()} {self.target} by {self.delta_pct:.0%} — {self.reason}"


class RebalancingEngine:
    def recommend(self, reg: PortfolioRegistry, *,
                  targets: dict[str, float], tolerance: float = 0.03
                  ) -> list[RebalanceAction]:
        """targets: desired % by key ('cash' or asset_class value). Emits actions
        for any class off-target beyond tolerance. Never executes anything."""
        alloc = AllocationEngine().allocate(reg)
        current = {"cash": alloc.cash_pct, **alloc.by_class}
        actions: list[RebalanceAction] = []
        for key, target in targets.items():
            cur = current.get(key, 0.0)
            drift = cur - target
            if abs(drift) > tolerance:
                actions.append(RebalanceAction(
                    action="reduce" if drift > 0 else "increase",
                    target=key, delta_pct=round(abs(drift), 4),
                    reason=f"at {cur:.0%}, target {target:.0%}"))
        actions.sort(key=lambda a: a.delta_pct, reverse=True)
        return actions


# ── Portfolio Impact Simulator (evaluate an opportunity IN the portfolio) ───
@dataclass
class ImpactReport:
    before: HealthReport
    after: HealthReport
    delta_health: float
    delta_concentration: float
    delta_volatility: float
    delta_liquidity: float
    improves: bool
    recommendation: str

    def render(self) -> str:
        arrow = "↑" if self.improves else "↓"
        return (f"🔬 Impact {arrow} health {self.before.overall:.0f}→{self.after.overall:.0f} "
                f"({self.delta_health:+.1f}) · {self.recommendation}")


class PortfolioImpactSimulator:
    """Answer 'should we add this, given everything we already own?' — never
    mutates the live registry."""

    def simulate(self, reg: PortfolioRegistry, new_position: Position, *,
                 monthly_burn_usd: float = 0.0,
                 correlation_matrix: dict[tuple[str, str], float] | None = None
                 ) -> ImpactReport:
        hs = PortfolioHealthScore()
        rk = PortfolioRiskEngine()
        before_h = hs.compute(reg, monthly_burn_usd=monthly_burn_usd,
                              correlation_matrix=correlation_matrix)
        before_r = rk.assess(reg, monthly_burn_usd=monthly_burn_usd,
                             correlation_matrix=correlation_matrix)

        after_reg = reg.clone()
        after_reg.add_position(replace(new_position), fund_from_cash=True)
        after_h = hs.compute(after_reg, monthly_burn_usd=monthly_burn_usd,
                            correlation_matrix=correlation_matrix)
        after_r = rk.assess(after_reg, monthly_burn_usd=monthly_burn_usd,
                           correlation_matrix=correlation_matrix)

        d_health = round(after_h.overall - before_h.overall, 1)
        improves = d_health >= 0
        rec = ("adds diversified, health-improving exposure" if improves
               else "worsens portfolio health — concentration/volatility rises")
        return ImpactReport(
            before=before_h, after=after_h, delta_health=d_health,
            delta_concentration=round(after_r.concentration - before_r.concentration, 4),
            delta_volatility=round(after_r.weighted_volatility - before_r.weighted_volatility, 4),
            delta_liquidity=round(after_r.liquidity - before_r.liquidity, 4),
            improves=improves, recommendation=rec)


# ── Capital Reserve Engine (financial vs business — every dollar competes) ──
class ReserveKind(str, Enum):
    FINANCIAL = "financial"           # crypto, stocks, ETF…
    BUSINESS = "business"             # cafeteria equipment, new location
    GROWTH = "growth"                 # marketing, YouTube push
    STRATEGIC = "strategic"           # SaathiAI feature, long-term moat


@dataclass
class ReserveOption:
    name: str
    kind: ReserveKind
    expected_return: float            # roi multiple (0.28 = +28%)
    risk: float                       # 0..1
    strategic_value: float            # 0..1
    confidence: float                 # 0..1
    time_to_payoff_months: float
    capital_required_usd: float

    @property
    def score(self) -> float:
        import math
        t = 1.0 / math.sqrt(max(1.0, self.time_to_payoff_months))
        return round(self.expected_return * (1 - self.risk) * self.strategic_value
                     * self.confidence * t, 4)


@dataclass
class ReserveDecision:
    available_usd: float
    ranked: list[ReserveOption]
    recommended: ReserveOption
    rationale: str


class CapitalReserveEngine:
    """The best investment isn't always in the market. Compares financial assets
    against business expansion, growth spend, and strategic build — while never
    dipping below the emergency reserve floor."""

    def allocate(self, available_usd: float, options: list[ReserveOption], *,
                 emergency_floor_usd: float = 0.0) -> ReserveDecision:
        spendable = max(0.0, available_usd - emergency_floor_usd)
        affordable = [o for o in options if o.capital_required_usd <= spendable]
        if not affordable:
            raise ValueError("no option affordable after emergency reserve floor")
        ranked = sorted(affordable, key=lambda o: o.score, reverse=True)
        best = ranked[0]
        rationale = (f"${spendable:,.0f} deployable → {best.name} [{best.kind.value}] "
                     f"(risk-adjusted score {best.score}) beats "
                     f"{len(affordable) - 1} alternatives across financial and business")
        return ReserveDecision(spendable, ranked, best, rationale)
