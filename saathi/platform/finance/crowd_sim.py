"""Swarm crowd-simulation for market prediction — a lightweight, deterministic port of the
MiroFish idea (github.com/666ghj/MiroFish) into SaathiOS, with NO external deps (no Zep, no
camel/OASIS, no paid LLM). Instead of thousands of LLM agents, it runs a small crowd of
investor-persona archetypes whose stances are computed from SaathiOS's own real evidence
(technical signals + strategy-playbook matches + catalyst news), then lets sentiment herd
over several rounds until it converges to an emergent direction.

Research/education only — a simulated crowd's opinion, never advice and never an order.
"""
from __future__ import annotations

from typing import Any

from saathi.platform.market_data import strategy_playbook, symbol_news
from saathi.platform.market_data.technical_analysis import signals_only

AUTHORITY = {
    "authority": "research_only",
    "disclaimer": "Emergent opinion of a simulated investor crowd over real evidence — research/education only, not advice, never an order.",
}

# Persona archetypes. `weight` = voice in the crowd; `herd` = how much it drifts toward the
# crowd's current mood each round (0 = ignores others, 1 = pure follower).
_PERSONAS = [
    {"id": "momentum", "label": "Momentum chaser", "weight": 1.2, "herd": 0.35},
    {"id": "technical", "label": "Technical trader", "weight": 1.3, "herd": 0.15},
    {"id": "value", "label": "Value investor", "weight": 1.0, "herd": 0.05},
    {"id": "dividend", "label": "Dividend hunter", "weight": 0.9, "herd": 0.10},
    {"id": "contrarian", "label": "Contrarian", "weight": 0.8, "herd": -0.20},
    {"id": "panic", "label": "Panic seller", "weight": 1.0, "herd": 0.45},
    {"id": "supply", "label": "Lock-in supply watcher", "weight": 1.1, "herd": 0.10},
    {"id": "retail", "label": "Retail herd", "weight": 1.4, "herd": 0.70},
]

_BULL = ("dividend", "bonus", "right")
_BEAR = ("lock", "promoter", "delist", "auction")


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _catalyst(symbol: str) -> dict[str, Any]:
    """Classify the freshest symbol catalyst into a signed pressure (+bull / -bear)."""
    try:
        news = symbol_news.symbol_news(symbol, limit=8)
    except Exception:
        news = {"events": []}
    for e in news.get("events", []):
        if not e.get("catalyst"):
            continue
        text = ((e.get("headline") or "") + " " + str(e.get("event_type") or "")).lower()
        if any(k in text for k in _BEAR):
            return {"type": "supply", "sign": -1, "label": e.get("headline"), "date": e.get("date")}
        if any(k in text for k in _BULL):
            return {"type": "distribution", "sign": +1, "label": e.get("headline"), "date": e.get("date")}
    return {"type": "none", "sign": 0, "label": None, "date": None}


def _base_stances(ev: dict[str, Any], matches: list[dict], cat: dict) -> list[dict[str, Any]]:
    """Each persona's evidence-anchored stance in [-1, 1] (sell … buy) + a reason."""
    trend = ev.get("trend")
    rsi = ev.get("rsi14")
    chg = ev.get("change_pct") or 0.0
    n_bull = len(matches)              # playbook setups are all long-biased
    top_score = max((m["score"] for m in matches), default=0.0)
    trend_s = 1.0 if trend == "UPTREND" else -1.0 if trend == "DOWNTREND" else 0.0
    cat_sign = cat.get("sign", 0)

    def rsi_dev():
        if rsi is None:
            return 0.0
        return (rsi - 50.0) / 50.0  # -1 … +1

    out = []
    for p in _PERSONAS:
        pid = p["id"]
        if pid == "momentum":
            s = 0.6 * trend_s + 0.4 * _clamp(chg / 3.0)
            why = f"trend {trend}, {chg:+.1f}% today"
        elif pid == "technical":
            s = 0.5 * trend_s + 0.5 * _clamp(n_bull / 3.0) * (1 if top_score >= 0.7 else 0.6)
            why = f"{n_bull} playbook setup(s), top score {int(top_score*100)}%"
        elif pid == "value":
            # cheap when beaten down (proxy: negative rsi deviation), fades strength
            s = _clamp(-0.6 * rsi_dev())
            why = f"RSI {rsi} — {'cheap' if s > 0 else 'not cheap'} on the pullback proxy"
        elif pid == "dividend":
            s = 0.7 if cat_sign > 0 else 0.1 * trend_s
            why = "dividend/bonus catalyst" if cat_sign > 0 else "no income catalyst"
        elif pid == "contrarian":
            s = _clamp(-1.0 * rsi_dev())  # fades extremes
            why = f"fades RSI {rsi}"
        elif pid == "panic":
            s = -0.8 if (cat_sign < 0 and trend_s <= 0) else -0.4 if trend_s < 0 else 0.0
            why = "negative catalyst + weak trend" if (cat_sign < 0 and trend_s <= 0) else f"trend {trend}"
        elif pid == "supply":
            s = -0.8 if cat_sign < 0 else 0.0
            why = f"supply overhang: {cat.get('label')}" if cat_sign < 0 else "no lock-in/supply event"
        else:  # retail — starts neutral, mostly herds later
            s = 0.2 * trend_s
            why = "waits for the crowd"
        out.append({"id": pid, "label": p["label"], "weight": p["weight"], "herd": p["herd"],
                    "base": round(_clamp(s), 3), "stance": round(_clamp(s), 3), "rationale": why})
    return out


def _aggregate(agents: list[dict]) -> float:
    tw = sum(a["weight"] for a in agents) or 1.0
    return sum(a["stance"] * a["weight"] for a in agents) / tw


def _run_rounds(agents: list[dict], rounds: int) -> list[float]:
    """Herd stances toward the crowd mood each round; return the sentiment trajectory."""
    traj = [round(_aggregate(agents), 3)]
    for _ in range(max(1, rounds)):
        mood = _aggregate(agents)
        for a in agents:
            # drift toward mood by herd factor, but stay anchored to evidence base (50/50 pull)
            target = a["base"] + a["herd"] * (mood - a["base"])
            a["stance"] = round(_clamp(0.5 * a["stance"] + 0.5 * target), 3)
        traj.append(round(_aggregate(agents), 3))
    return traj


def _dispersion(agents: list[dict]) -> float:
    xs = [a["stance"] for a in agents]
    m = sum(xs) / len(xs)
    var = sum((x - m) ** 2 for x in xs) / len(xs)
    return var ** 0.5  # 0 = full agreement


def simulate(market: str, symbol: str, rounds: int = 6) -> dict[str, Any]:
    sig = signals_only(market, symbol, "1d")
    if not sig.get("available"):
        return {"available": False, "market": market, "symbol": symbol,
                "error": sig.get("error") or "no data", **AUTHORITY}
    ev = sig.get("evidence") or {}
    matches = (strategy_playbook.scan(market, symbol).get("matches") or []) if True else []
    cat = _catalyst(symbol) if market == "NEPSE" else {"type": "none", "sign": 0, "label": None, "date": None}

    agents = _base_stances(ev, matches, cat)
    traj = _run_rounds(agents, rounds)
    sentiment = traj[-1]
    disp = _dispersion(agents)
    agreement = _clamp(1.0 - disp, 0.0, 1.0)

    direction = "UP" if sentiment > 0.15 else "DOWN" if sentiment < -0.15 else "SIDEWAYS"
    confidence = round(_clamp(abs(sentiment) * 0.6 + agreement * 0.4, 0.0, 1.0), 2)

    bulls = [a for a in agents if a["stance"] > 0.15]
    bears = [a for a in agents if a["stance"] < -0.15]
    drivers = []
    if cat["sign"] < 0:
        drivers.append(f"Supply/negative catalyst: {cat['label']}")
    elif cat["sign"] > 0:
        drivers.append(f"Positive catalyst: {cat['label']}")
    drivers.append(f"Trend {ev.get('trend')}, RSI {ev.get('rsi14')}, {ev.get('change_pct')}% last")
    if matches:
        drivers.append(f"{len(matches)} bullish playbook setup(s) active")

    narrative = (
        f"A simulated crowd of {len(agents)} investor archetypes read {market} {symbol} over "
        f"{rounds} rounds. Sentiment settled at {sentiment:+.2f} ({direction}), with "
        f"{len(bulls)} leaning buy and {len(bears)} leaning sell (agreement {int(agreement*100)}%). "
        + (f"The dominant driver is {drivers[0].lower()}. " if drivers else "")
        + "This is an emergent opinion of a model crowd, not a forecast of fact."
    )

    return {
        "available": True, "market": market, "symbol": symbol,
        "direction": direction, "sentiment": sentiment, "confidence": confidence,
        "agreement": round(agreement, 2), "rounds": rounds, "trajectory": traj,
        "catalyst": cat, "drivers": drivers,
        "agents": [{"persona": a["label"], "stance": a["stance"], "base": a["base"],
                    "lean": "BUY" if a["stance"] > 0.15 else "SELL" if a["stance"] < -0.15 else "HOLD",
                    "rationale": a["rationale"]} for a in agents],
        "evidence": {k: ev.get(k) for k in ("last", "trend", "rsi14", "change_pct", "ema21", "ema50")},
        "narrative": narrative,
        **AUTHORITY,
    }
