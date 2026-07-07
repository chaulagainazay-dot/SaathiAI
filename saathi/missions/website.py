"""Website Intelligence & Design Director.

Understands how a website works (stack, UX, SEO, design patterns), never copies it,
and turns that understanding into an ORIGINAL, Mission-branded design system + build
blueprint. Everything is grounded in real fetched HTML — no invented metrics — and
flows into the Mission Knowledge Graph, Research Library, Timeline, and (via the
Proposal Director) a client proposal.

Honest scope: analysis is from fetched HTML (real). Screenshots / Lighthouse field
data / live-render competitor scraping are DEFERRED (need headless-browser infra) —
this never fabricates a metric it didn't measure.
"""
from __future__ import annotations

import re

# stack fingerprints (substring → framework)
_STACK = [
    ("__NEXT_DATA__", "Next.js"), ("/_next/", "Next.js"), ("data-reactroot", "React"),
    ("react", "React"), ("wp-content", "WordPress"), ("wp-json", "WordPress"),
    ("cdn.shopify", "Shopify"), ("myshopify", "Shopify"), ("webflow", "Webflow"),
    ("framerusercontent", "Framer"), ("data-framer", "Framer"), ("gsap", "GSAP"),
    ("cdn.tailwindcss", "Tailwind"), ("bootstrap", "Bootstrap"), ("wix.com", "Wix"),
    ("squarespace", "Squarespace"), ("elementor", "Elementor"), ("gatsby", "Gatsby"),
    ("vercel", "Vercel"), ("cloudflare", "Cloudflare"),
]
_PATTERN_HINTS = {
    "hero section": ["hero", "banner", "jumbotron"], "testimonials": ["testimonial", "review", "what our"],
    "pricing cards": ["pricing", "per month", "/mo", "plan"], "booking widget": ["book now", "reserve", "check availability"],
    "gallery": ["gallery", "portfolio", "our work"], "mega menu": ["megamenu", "mega-menu"],
    "newsletter": ["subscribe", "newsletter"], "FAQ accordion": ["faq", "frequently asked"],
    "destination cards": ["destination", "package", "tour"], "cta band": ["get started", "contact us", "get a quote"],
}


def _fetch(url: str, timeout: float = 12.0) -> tuple[str, str]:
    import httpx
    if not url.startswith("http"):
        url = "https://" + url
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout,
                          headers={"User-Agent": "SaathiAI-WebIntel/1.0"}) as c:
            r = c.get(url)
            return (r.text or ""), str(r.url)
    except Exception:
        return "", url


def detect_stack(html: str) -> list[str]:
    low = html.lower()
    return sorted({name for token, name in _STACK if token.lower() in low})


def seo_signals(html: str, url: str) -> dict:
    low = html.lower()
    def has(rx):
        return bool(re.search(rx, html, re.I))
    title = (re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S) or [None, ""])[1].strip()[:120]
    desc = has(r'<meta[^>]+name=["\']description["\']')
    h1 = len(re.findall(r"<h1", low)); h2 = len(re.findall(r"<h2", low))
    score, issues, wins = 100, [], []
    if not title:
        score -= 20; issues.append("Missing <title>")
    else:
        wins.append("Has title")
    if not desc:
        score -= 20; issues.append("Missing meta description")
    else:
        wins.append("Has meta description")
    if h1 == 0:
        score -= 15; issues.append("No H1")
    elif h1 > 1:
        score -= 5; issues.append(f"{h1} H1 tags (should be 1)")
    if not has(r'application/ld\+json'):
        score -= 10; issues.append("No schema.org structured data")
    else:
        wins.append("Structured data present")
    if not has(r'og:title'):
        score -= 10; issues.append("No Open Graph tags")
    if not has(r'rel=["\']canonical["\']'):
        score -= 5; issues.append("No canonical tag")
    if not url.startswith("https"):
        score -= 15; issues.append("Not HTTPS")
    return {"gathered": bool(html), "score": max(0, score), "title": title, "headings": {"h1": h1, "h2": h2},
            "issues": issues, "wins": wins}


def ux_signals(html: str) -> dict:
    low = html.lower()
    imgs = len(re.findall(r"<img", low))
    alts = len(re.findall(r"<img[^>]+alt=", low))
    forms = len(re.findall(r"<form", low))
    ctas = len(re.findall(r"(book now|get started|contact us|sign up|buy now|get a quote|subscribe)", low))
    nav = "mega menu" if ("megamenu" in low or "mega-menu" in low) else ("nav" if "<nav" in low else "unknown")
    responsive = bool(re.search(r'name=["\']viewport["\']', html, re.I))
    animated = any(k in low for k in ("gsap", "framer", "aos", "animate", "scroll"))
    return {"images": imgs, "images_with_alt": alts, "alt_coverage": round(alts / imgs, 2) if imgs else 0,
            "forms": forms, "cta_count": ctas, "nav": nav, "responsive": responsive, "animated": animated}


def design_patterns(html: str) -> list[str]:
    low = html.lower()
    found = [name for name, kws in _PATTERN_HINTS.items() if any(k in low for k in kws)]
    return found


def analyze_site(url: str) -> dict:
    html, final = _fetch(url)
    ok = bool(html)
    return {"url": final, "ok": ok, "stack": detect_stack(html), "seo": seo_signals(html, final),
            "ux": ux_signals(html), "patterns": design_patterns(html),
            "note": "" if ok else "could not fetch"}


# ── Mission-branded ORIGINAL design system (never copied) ─────────────────────
_DEPT_STYLE = {
    "travel":    {"mood": "warm, adventurous", "palette": ["#0E7C86", "#F4A259", "#FFF7ED", "#12303A"],
                  "heading": "Fraunces / Playfair", "body": "Inter"},
    "education": {"mood": "patient, trustworthy", "palette": ["#6C3FCF", "#00BFA5", "#0F1226", "#F5F5FF"],
                  "heading": "Sora", "body": "Inter"},
    "hcg":       {"mood": "confident, analytical", "palette": ["#0B0F1A", "#FF5A5A", "#00E0B8", "#E6E9F2"],
                  "heading": "Space Grotesk", "body": "IBM Plex Sans"},
    "cafeteria": {"mood": "fresh, appetising", "palette": ["#2E7D32", "#FFB74D", "#FFFDF7", "#33291E"],
                  "heading": "Poppins", "body": "Inter"},
}


def design_system(mission: dict) -> dict:
    dept = mission.get("department", "")
    brand = {}
    try:
        from saathi.missions.brand import default_store as b_store, default_brand
        brand = b_store().get_brand(mission.get("id", "")) or default_brand(mission)
    except Exception:
        pass
    style = _DEPT_STYLE.get(dept, {"mood": "modern, premium", "palette": ["#111827", "#6366F1", "#F9FAFB", "#4B5563"],
                                   "heading": "Sora", "body": "Inter"})
    palette = brand.get("colors") or style["palette"]
    return {
        "mood": style["mood"],
        "palette": palette,
        "typography": {"heading": style["heading"], "body": style["body"], "scale": "1.25 major-third"},
        "spacing": [4, 8, 12, 16, 24, 32, 48, 64],
        "radius": {"sm": 8, "md": 12, "lg": 20, "pill": 999},
        "components": ["Button (primary/ghost)", "Card", "Input", "Nav", "Hero", "Footer", "Pricing card", "Testimonial"],
        "motion": "200–300ms ease-out; scroll-reveal on sections; no autoplay",
        "photography": "authentic, on-brand; consistent colour grade",
        "accessibility": "WCAG AA contrast, focus rings, semantic headings, alt text",
        "note": "Original tokens derived from this Mission's brand + sector — not copied from any reference site.",
    }


def wireframe_outline(mission: dict, patterns: list[str]) -> list[dict]:
    pages = ["Home", "About", "Services", "Pricing", "Contact"]
    if mission.get("department") == "travel":
        pages = ["Home", "Destinations", "Packages", "About", "Booking", "Contact"]
    return [{"page": p, "sections": ["Nav", "Hero (headline + CTA)", "Value props", "Social proof",
             "Feature/section grid", "CTA band", "Footer"], "primary_cta": "Get a quote"} for p in pages]


def frontend_blueprint(mission: dict) -> dict:
    return {"stack": ["Next.js", "React", "TypeScript", "Tailwind CSS", "shadcn/ui", "Framer Motion"],
            "structure": ["app/ (routes)", "components/ui", "components/sections", "lib/", "content/ (CMS)"],
            "cms": "Markdown/MDX or a headless CMS for pages+blog",
            "apis": ["contact/booking form → email + CRM", "analytics", "SEO metadata per route"],
            "seo": "per-route metadata, sitemap, schema.org, OG images",
            "performance": ["image optimisation", "lazy sections", "font preload", "Lighthouse 90+"],
            "deployment": "Vercel (preview per PR)"}


def intelligence(mission_key: str, url: str, *, compare_url: str = "") -> dict:
    """Full pipeline: analyse → patterns → Mission-branded design → store → report."""
    from saathi.missions.store import default_store as m_store
    ms = m_store()
    mission = ms.get(mission_key) or ms.get_by_key(mission_key) or {}
    mid = mission.get("id", "")

    ref = analyze_site(url)
    client = analyze_site(compare_url) if compare_url else None
    ds = design_system(mission)
    wires = wireframe_outline(mission, ref.get("patterns", []))
    blueprint = frontend_blueprint(mission)

    # store in Knowledge Graph + Research Library + Timeline
    if mid:
        try:
            from saathi.missions.knowledge import default_graph
            g = default_graph()
            g.upsert(mid, "website", f"ref-{re.sub(r'\\W+','-',url)[:30]}", label=url,
                     data={"stack": ref["stack"], "seo_score": ref["seo"].get("score"),
                           "patterns": ref["patterns"], "role": "reference"}, source="web_intel")
            for p in ref.get("patterns", []):
                g.upsert(mid, "asset", f"pattern-{p.replace(' ', '-')}", label=p,
                         data={"kind": "design_pattern", "from": url}, source="web_intel")
        except Exception:
            pass
        try:
            from saathi.knowledge_library.store import default_store as lib
            lib().add(title=f"Design reference: {ref['seo'].get('title') or url}", url=ref["url"],
                      source_type="doc", category="Design", summary=f"Stack {', '.join(ref['stack']) or 'n/a'}; "
                      f"patterns {', '.join(ref['patterns']) or 'n/a'}", tags=ref["stack"] + ref["patterns"],
                      related_directors=["creative", "publishing"])
        except Exception:
            pass
        try:
            from saathi.missions.timeline import default_store as tl
            tl().record(mid, "research", f"Website analysed: {url}",
                        detail=f"stack {', '.join(ref['stack']) or 'n/a'} · SEO {ref['seo'].get('score')}/100 · "
                               f"{len(ref['patterns'])} patterns → original design system generated")
        except Exception:
            pass

    comparison = None
    if client:
        comparison = {"reference_seo": ref["seo"].get("score"), "client_seo": client["seo"].get("score"),
                      "client_stack": client["stack"], "gap": (ref["seo"].get("score", 0) - client["seo"].get("score", 0))}

    return {"mission": mission_key, "reference": ref, "client": client, "comparison": comparison,
            "design_patterns": ref.get("patterns", []), "design_system": ds,
            "wireframes": wires, "blueprint": blueprint,
            "principle": "Original design generated from the Mission's brand + sector. Reference used for "
                         "pattern recognition only — nothing copied."}
