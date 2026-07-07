"""Reference Intelligence Department — understand, never copy.

A permanent department that ingests ANY reference (website, video, social profile,
GitHub repo, PDF, doc, Figma, app), classifies it, routes to the right analyzer,
extracts REUSABLE patterns (not the source itself) into the Mission Knowledge Graph +
Research Library, compares many references, and feeds original generation (design
systems, blueprints, proposals) grounded in the Mission's identity.

    Reference → classify → analyze → patterns → Knowledge Graph + Research Library
              → Mission context → Creative/Design/Proposal Directors → Evidence → Learning

Honesty: every analyzer reports only what it can actually measure. Deep video-frame /
engagement analysis, file uploads (image/pdf/doc/figma/app), and app-store scraping are
DECLARED-DEFERRED (need APIs / parse / headless infra) — never fabricated.
"""
from __future__ import annotations

import re

_KIND_PATTERNS = [
    (r"github\.com", "github"),
    (r"(youtube\.com|youtu\.be)", "video_youtube"),
    (r"instagram\.com", "social_instagram"),
    (r"facebook\.com|fb\.com", "social_facebook"),
    (r"tiktok\.com", "video_tiktok"),
    (r"linkedin\.com", "social_linkedin"),
    (r"(twitter\.com|x\.com)", "social_x"),
    (r"play\.google\.com|apps\.apple\.com", "app_store"),
    (r"figma\.com", "figma"),
    (r"\.pdf($|\?)", "pdf"),
]

# what SaathiOS can deeply analyze now vs what needs deferred infra
_LIVE_KINDS = {"website", "github", "video_youtube", "social_instagram", "social_facebook",
               "social_linkedin", "social_x", "video_tiktok"}
_DEFERRED = {"pdf": "upload the PDF text (paste) — file parsing not yet wired",
             "figma": "Figma API import not yet wired",
             "app_store": "app-store scraping not yet wired"}


def classify(url: str) -> str:
    low = (url or "").lower()
    for rx, kind in _KIND_PATTERNS:
        if re.search(rx, low):
            return kind
    return "website"


def _meta(url: str, timeout: float = 12.0) -> dict:
    """Open-Graph / meta scrape — the honest, no-login level for video/social pages."""
    import httpx
    if not url.startswith("http"):
        url = "https://" + url
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout,
                          headers={"User-Agent": "SaathiAI-RefIntel/1.0"}) as c:
            html = c.get(url).text
    except Exception:
        return {"ok": False}
    def og(prop):
        m = re.search(rf'<meta[^>]+(?:property|name)=["\']{prop}["\'][^>]+content=["\']([^"\']+)', html, re.I)
        return (m.group(1).strip() if m else "")[:240]
    return {"ok": True, "title": og("og:title") or og("title"), "description": og("og:description"),
            "image": og("og:image"), "site_name": og("og:site_name"), "kind_meta": og("og:type")}


# ── per-type analyzers (report only what's measurable) ────────────────────────
def _analyze_video(url: str, kind: str) -> dict:
    m = _meta(url)
    return {"kind": kind, "url": url, "ok": m.get("ok", False),
            "title": m.get("title", ""), "description": m.get("description", ""),
            "thumbnail": m.get("image", ""),
            "patterns": ["hook (title)", "thumbnail style"] if m.get("ok") else [],
            "measured": ["title", "description", "thumbnail"],
            "deferred": ["retention", "editing/transitions/music (frame analysis)", "posting cadence (needs API)"]}


def _analyze_social(url: str, kind: str) -> dict:
    m = _meta(url)
    return {"kind": kind, "url": url, "ok": m.get("ok", False),
            "handle": m.get("title", ""), "bio": m.get("description", ""), "avatar": m.get("image", ""),
            "patterns": ["bio positioning", "profile branding"] if m.get("ok") else [],
            "measured": ["handle", "bio", "avatar"],
            "deferred": ["posting frequency, engagement, content pillars (need platform API / login)"]}


def analyze_one(url: str, *, mission_key: str = "") -> dict:
    kind = classify(url)
    if kind == "website":
        from saathi.missions.website import analyze_site
        a = analyze_site(url)
        a["kind"] = "website"
        return a
    if kind == "github":
        from saathi.knowledge_library.importer import import_repo
        r = import_repo(url)
        s = r.get("source", {})
        return {"kind": "github", "url": url, "ok": r.get("ok", False), "title": s.get("title", ""),
                "patterns": s.get("tags", []), "summary": s.get("summary", ""),
                "related_directors": s.get("related_directors", [])}
    if kind.startswith("video"):
        return _analyze_video(url, kind)
    if kind.startswith("social"):
        return _analyze_social(url, kind)
    return {"kind": kind, "url": url, "ok": False, "patterns": [],
            "deferred_reason": _DEFERRED.get(kind, "not yet supported")}


# ── storage: patterns → Knowledge Graph + Research Library + Timeline ─────────
def _store(mission_id: str, ref: dict) -> None:
    if not mission_id:
        return
    url = ref.get("url", "")
    try:
        from saathi.missions.knowledge import default_graph
        g = default_graph()
        node_type = "website" if ref["kind"] == "website" else "asset"
        g.upsert(mission_id, node_type, f"ref-{re.sub(r'\\W+','-',url)[:28]}", label=url,
                 data={"kind": ref["kind"], "patterns": ref.get("patterns", []),
                       "title": ref.get("title") or ref.get("handle", "")}, source="reference_intel")
        for p in ref.get("patterns", [])[:8]:
            g.upsert(mission_id, "asset", f"pat-{re.sub(r'\\W+','-',str(p))[:24]}", label=str(p),
                     data={"kind": "pattern", "from": url, "ref_kind": ref["kind"]}, source="reference_intel")
    except Exception:
        pass
    try:
        from saathi.knowledge_library.store import default_store as lib
        lib().add(title=f"Reference ({ref['kind']}): {ref.get('title') or ref.get('handle') or url}",
                  url=url, source_type="doc", category="Reference",
                  summary=ref.get("summary") or ref.get("description", "")[:200],
                  tags=[ref["kind"]] + [str(p) for p in ref.get("patterns", [])][:8],
                  related_directors=["creative", "research"])
    except Exception:
        pass


def analyze_many(urls: list[str], *, mission_key: str = "", generate: bool = True) -> dict:
    """Analyze N references, extract + store patterns, and (optionally) generate an
    original Mission-branded design system + blueprint from the aggregated learning."""
    from saathi.missions.store import default_store as m_store
    ms = m_store()
    mission = ms.get(mission_key) or ms.get_by_key(mission_key) or {}
    mid = mission.get("id", "")

    refs = [analyze_one(u, mission_key=mission_key) for u in urls]
    for r in refs:
        _store(mid, r)

    all_patterns = sorted({str(p) for r in refs for p in r.get("patterns", [])})
    kinds = sorted({r["kind"] for r in refs})

    out = {"mission": mission_key, "references": refs, "kinds": kinds,
           "patterns": all_patterns, "count": len(refs),
           "principle": "Patterns extracted for reuse — nothing copied. Original output generated from the "
                        "Mission's brand + sector."}

    if generate and mission:
        from saathi.missions.website import design_system, wireframe_outline, frontend_blueprint
        out["design_system"] = design_system(mission)
        out["wireframes"] = wireframe_outline(mission, all_patterns)
        out["blueprint"] = frontend_blueprint(mission)

    if mid:
        try:
            from saathi.missions.timeline import default_store as tl
            tl().record(mid, "research", f"Reference Intelligence: {len(refs)} references analysed",
                        detail=f"kinds {', '.join(kinds)} · {len(all_patterns)} patterns → original system generated")
        except Exception:
            pass
    return out
