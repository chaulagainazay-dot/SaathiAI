"""M — RESEARCH_SURFACE_UI_WIRING — thin read-only BFF over the research intelligence.

The backend intelligence projection is authoritative. This module exposes it to the
product surfaces (Central Command API, chat, voice) WITHOUT re-implementing any
event clustering / authority / reconciliation / freshness / priority on the way out.
READ-ONLY. No gateway, Trading Guardian, broker, portfolio, or market_data writes.
"""
from __future__ import annotations

import time

from saathi.browser_research.intelligence import (
    build_from_evidence, central_command_projection, chat_answer, daily_brief,
    voice_answer,
)

MARKET_DEFAULT = "NEPSE"

# lightweight cache so a UI render never triggers collection or a full rebuild.
_CACHE: dict = {"snapshot": None, "built_at": 0.0, "market": ""}
_TTL = 30.0


def _store():
    from saathi.evidence.store import default_store
    return default_store()


def _snapshot(*, store=None, market: str = MARKET_DEFAULT, holdings=None, fresh: bool = False):
    now = time.time()
    if (not fresh and store is None and _CACHE["snapshot"] is not None
            and _CACHE["market"] == market and (now - _CACHE["built_at"]) < _TTL):
        return _CACHE["snapshot"]
    snap = build_from_evidence(store or _store(), market=market, now=now, holdings=holdings)
    if store is None:
        _CACHE.update(snapshot=snap, built_at=now, market=market)
    return snap


def _source_health(snap) -> dict:
    # Health is derived from what evidence exists + endpoint monitor when a live
    # capture is available; here we project stored-evidence availability.
    from saathi.browser_research.intelligence import unify_source_health
    docs = [{"source_url": d.get("source_url", ""), "status": d.get("status", "")}
            for d in snap.documents]
    have = bool(snap.events)
    return unify_source_health(
        sebon_status="AVAILABLE" if have else "UNKNOWN",
        nrb_status="AVAILABLE" if have else "UNKNOWN",
        documents=docs)


# ── Central Command API projections (read-only) ──────────────────────────────
def intelligence(*, store=None, market: str = MARKET_DEFAULT, holdings=None) -> dict:
    snap = _snapshot(store=store, market=market, holdings=holdings)
    proj = central_command_projection(snap)
    proj["source_health"] = _source_health(snap)
    proj["state"] = "EMPTY" if not snap.events else "OK"
    proj["generated_at"] = snap.generated_at
    proj["read_only"] = True
    return proj


def events(*, store=None, market: str = MARKET_DEFAULT, holdings=None, limit: int = 50) -> dict:
    snap = _snapshot(store=store, market=market, holdings=holdings)
    return {"read_only": True, "market": market, "count": len(snap.events),
            "events": [e.as_dict() for e in snap.events[:limit]]}


def event_detail(event_id: str, *, store=None, market: str = MARKET_DEFAULT, holdings=None) -> dict:
    snap = _snapshot(store=store, market=market, holdings=holdings)
    for e in snap.events:
        if e.event_id == event_id:
            d = e.as_dict()
            d["read_only"] = True
            return d
    return {"read_only": True, "error": "EVENT_NOT_FOUND", "event_id": event_id}


def brief(*, store=None, market: str = MARKET_DEFAULT, holdings=None) -> dict:
    snap = _snapshot(store=store, market=market, holdings=holdings)
    b = daily_brief(snap)
    b["read_only"] = True
    b["state"] = "EMPTY" if not snap.events else "OK"
    return b


def health(*, store=None, market: str = MARKET_DEFAULT) -> dict:
    snap = _snapshot(store=store, market=market)
    return {"read_only": True, "source_health": _source_health(snap),
            "events": len(snap.events), "generated_at": snap.generated_at}


# ── chat / voice hooks (same snapshot; evidence-backed; no fabrication) ───────
_RESEARCH_HINTS = (
    "nepse", "sebon", "nrb", "dividend", "bonus", "right share", "rights", "agm",
    "disclosure", "disclosures", "notice", "corporate action", "book close",
    "delist", "listing", "monetary policy", "research", "contradict", "official event",
    "what changed", "brief", "announcement",
)


def is_research_query(text: str) -> bool:
    t = (text or "").lower()
    return any(h in t for h in _RESEARCH_HINTS)


def maybe_answer_chat(text: str, *, store=None, market: str = MARKET_DEFAULT):
    """Return an evidence-backed reply dict for a research query, else None."""
    if not is_research_query(text):
        return None
    snap = _snapshot(store=store, market=market)
    if "brief" in (text or "").lower():
        b = daily_brief(snap)
        n = len(b.get("what_changed", []))
        return {"reply": f"Today's {market} brief: {n} notable events. "
                + "; ".join(x["headline"][:60] for x in b.get("what_changed", [])[:3])
                + (" (no official events yet)" if not snap.events else ""),
                "evidence_refs": snap.evidence_refs[:20], "supported": bool(snap.events)}
    ans = chat_answer(snap, text)
    refs = []
    for e in ans.get("events", [])[:5]:
        refs.extend(e.get("evidence_refs", []))
    return {"reply": ans["answer"], "events": ans.get("events", [])[:5],
            "evidence_refs": refs, "supported": ans.get("supported", False)}


def maybe_answer_voice(text: str, *, store=None, market: str = MARKET_DEFAULT):
    if not is_research_query(text):
        return None
    snap = _snapshot(store=store, market=market)
    if "brief" in (text or "").lower():
        b = daily_brief(snap)
        top = b.get("what_changed", [])[:1]
        return {"reply": f"{market} brief: " + (top[0]["headline"][:80] if top else "no new official events.")}
    return {"reply": voice_answer(snap)}
