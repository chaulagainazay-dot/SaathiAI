"""Mission Intake — the front door of every business.

Manual entry that immediately raises Knowledge Coverage without any OAuth: connect
accounts (as handles/URLs), enter social stats, revenue, services, customers, and
paste documents for extraction. Every field becomes a Knowledge Graph node, so the
Digital Twin, Proposal, and Learning all get richer the moment a form is filled.
Two minutes of typing beats a week of OAuth plumbing — and tells us later which
connectors are actually worth building.
"""
from __future__ import annotations

import re

_ACCOUNTS = ("website", "facebook", "instagram", "tiktok", "youtube",
             "google_business", "telegram", "whatsapp", "linkedin", "twitter")


def _split(v) -> list[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        return [s.strip() for s in re.split(r"[,\n;]", v) if s.strip()]
    return []


def apply_intake(mission_id: str, data: dict, *, graph=None) -> dict:
    """Write a structured intake payload into the Business Memory. Returns nodes_added + coverage."""
    from saathi.missions.knowledge import default_graph
    g = graph or default_graph()
    n = 0

    # accounts / channels (handles or URLs — not OAuth)
    accounts = data.get("accounts") or {}
    for plat in _ACCOUNTS:
        val = accounts.get(plat) or data.get(plat)
        if not val:
            continue
        ntype = "website" if plat == "website" else "social_channel" if plat in (
            "facebook", "instagram", "tiktok", "youtube", "linkedin", "twitter") else "account"
        g.upsert(mission_id, ntype, plat, label=plat, data={"handle": val}, source="intake"); n += 1

    # social stats → kpi nodes (+ enrich the channel node)
    for k, v in (data.get("social_stats") or {}).items():
        if v in (None, ""):
            continue
        g.upsert(mission_id, "kpi", f"social.{k}", label=k.replace("_", " "),
                 data={"value": v, "kind": "social"}, source="intake"); n += 1

    # revenue (manual — Stripe later)
    rev = data.get("revenue")
    if isinstance(rev, dict) and rev.get("amount") not in (None, ""):
        g.upsert(mission_id, "revenue", f"rev-{rev.get('date', 'entry')}",
                 label=f"{rev.get('amount')} {rev.get('source', '')}".strip(),
                 data=rev, source="intake"); n += 1
    elif data.get("monthly_revenue"):
        g.upsert(mission_id, "revenue", "monthly", label=str(data["monthly_revenue"]),
                 data={"amount": data["monthly_revenue"], "period": "monthly"}, source="intake"); n += 1

    # services / products / customers
    for i, s in enumerate(_split(data.get("services"))):
        g.upsert(mission_id, "service", f"svc-{i}", label=s, data={"name": s}, source="intake"); n += 1
    for i, p in enumerate(_split(data.get("products"))):
        g.upsert(mission_id, "product", f"prod-{i}", label=p, data={"name": p}, source="intake"); n += 1
    for i, c in enumerate(_split(data.get("customers"))):
        g.upsert(mission_id, "customer", f"seg-{i}", label=c, data={"segment": c}, source="intake"); n += 1

    # brand + team + stack + goals as company-adjacent nodes
    if data.get("brand"):
        g.upsert(mission_id, "brand", "brand", label="Brand", data=data["brand"]
                 if isinstance(data["brand"], dict) else {"note": data["brand"]}, source="intake"); n += 1
    for i, t in enumerate(_split(data.get("team"))):
        g.upsert(mission_id, "employee", f"emp-{i}", label=t, data={"name": t}, source="intake"); n += 1
    for i, tool in enumerate(_split(data.get("current_stack"))):
        g.upsert(mission_id, "asset", f"tool-{i}", label=tool, data={"tool": tool}, source="intake"); n += 1
    for i, goal in enumerate(_split(data.get("goals"))):
        g.upsert(mission_id, "opportunity", f"goal-{i}", label=str(goal)[:60],
                 data={"text": goal, "kind": "goal"}, source="intake"); n += 1
    for i, prob in enumerate(_split(data.get("problems"))):
        g.upsert(mission_id, "risk", f"prob-{i}", label=str(prob)[:60],
                 data={"text": prob, "kind": "stated"}, source="intake"); n += 1

    cov = g.coverage(mission_id)
    return {"nodes_added": n, "coverage": cov["overall"], "categories": cov["categories"]}


# ── Document extraction (paste text now; file+OCR later) ──────────────────────
_PRICE = re.compile(r"(?:NPR|Rs\.?|₹|\$)\s?[\d,]+(?:\.\d+)?", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?:\+?\d[\d\s-]{7,}\d)")


def extract_document(mission_id: str, text: str, *, title: str = "", graph=None) -> dict:
    """Paste a document; pull out prices, emails, phones, and heading-like services
    into the Knowledge Graph. Heuristic now; LLM extraction can slot in later."""
    from saathi.missions.knowledge import default_graph
    g = graph or default_graph()
    text = text or ""
    prices = list(dict.fromkeys(_PRICE.findall(text)))[:12]
    emails = list(dict.fromkeys(_EMAIL.findall(text)))[:6]
    phones = list(dict.fromkeys(m.strip() for m in _PHONE.findall(text)))[:6]

    doc_key = re.sub(r"\W+", "-", (title or text[:24]).lower()).strip("-") or "document"
    g.upsert(mission_id, "document", doc_key, label=title or "Uploaded document",
             data={"chars": len(text), "prices": prices, "emails": emails, "phones": phones,
                   "excerpt": text[:280]}, source="upload")
    n = 1
    for i, pr in enumerate(prices):
        g.upsert(mission_id, "kpi", f"price-{doc_key}-{i}", label=f"Price: {pr}",
                 data={"value": pr, "kind": "price"}, source="upload"); n += 1
    for i, em in enumerate(emails):
        g.upsert(mission_id, "customer", f"contact-{em}", label=em,
                 data={"email": em}, source="upload"); n += 1

    cov = g.coverage(mission_id)
    return {"nodes_added": n, "extracted": {"prices": prices, "emails": emails, "phones": phones},
            "coverage": cov["overall"]}
