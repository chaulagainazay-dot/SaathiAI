"""Website Intelligence & Design Director — stack/SEO/UX/patterns + original design system."""
from saathi.missions.website import (detect_stack, seo_signals, ux_signals, design_patterns,
                                     design_system, wireframe_outline, frontend_blueprint)


_HTML = """<html><head><title>Acme Travel</title>
<meta name="description" content="Best tours in Nepal">
<meta property="og:title" content="Acme"><link rel="canonical" href="https://acme.com">
<script type="application/ld+json">{}</script>
<meta name="viewport" content="width=device-width"></head>
<body><nav>menu</nav><section class="hero">Explore Nepal <a>Book Now</a></section>
<div class="pricing">$500 per month</div><div class="testimonial">what our clients say</div>
<img src="a.jpg" alt="tour"><form></form>
<script src="/_next/static/x.js"></script><script src="gsap.min.js"></script></body></html>"""


def test_stack_detection_from_html():
    st = detect_stack(_HTML)
    assert "Next.js" in st and "GSAP" in st


def test_seo_signals_are_measured_not_invented():
    s = seo_signals(_HTML, "https://acme.com")
    assert s["gathered"] and s["title"] == "Acme Travel"
    assert "Has meta description" in s["wins"] and s["score"] >= 80
    assert "No H1" in s["issues"]                             # measured, not invented
    bad = seo_signals("<html></html>", "http://x.com")
    assert bad["score"] < 60 and "Missing <title>" in bad["issues"] and "Not HTTPS" in bad["issues"]


def test_ux_and_patterns():
    ux = ux_signals(_HTML)
    assert ux["cta_count"] >= 1 and ux["responsive"] and ux["animated"] and ux["forms"] == 1
    pats = design_patterns(_HTML)
    assert "hero section" in pats and "pricing cards" in pats and "testimonials" in pats


def test_design_system_is_mission_branded_original():
    ds_travel = design_system({"id": "M", "department": "travel"})
    ds_edu = design_system({"id": "M2", "department": "education"})
    assert ds_travel["palette"] != ds_edu["palette"]         # branded per sector
    assert "not copied" in ds_travel["note"].lower()
    assert ds_travel["typography"]["body"] and ds_travel["spacing"] and ds_travel["radius"]["pill"] == 999


def test_wireframes_and_blueprint():
    w = wireframe_outline({"department": "travel"}, [])
    pages = [p["page"] for p in w]
    assert "Destinations" in pages and "Booking" in pages
    bp = frontend_blueprint({})
    assert "Next.js" in bp["stack"] and "Tailwind CSS" in bp["stack"] and bp["deployment"]


def test_workspace_routes_website_urls():
    from saathi.workspace import _detect_website, detect_github
    assert _detect_website("analyze this website https://awwwards.com please") == "https://awwwards.com"
    assert _detect_website("check https://github.com/x/y") is None   # github goes to repo pipeline
