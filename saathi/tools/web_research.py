"""Live website + social research — Stage 2 of client intake.

Fetches the client's actual website (HTTP, no browser — works on the VM and the
Mac), extracts title / meta description / headings / visible text / detected
social profiles, so the AI research is grounded in the real site instead of only
the form answers. Graceful: any failure returns a partial result, never raises.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

_SOCIALS = {
    "facebook": r"facebook\.com/[^\"'\s>]+", "instagram": r"instagram\.com/[^\"'\s>]+",
    "tiktok": r"tiktok\.com/@?[^\"'\s>]+", "youtube": r"youtube\.com/[^\"'\s>]+",
    "linkedin": r"linkedin\.com/[^\"'\s>]+", "twitter": r"(?:twitter|x)\.com/[^\"'\s>]+",
    "pinterest": r"pinterest\.com/[^\"'\s>]+",
}


class _Extract(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title, self.desc = "", ""
        self.headings, self._text = [], []
        self._tag, self._skip = "", 0

    def handle_starttag(self, tag, attrs):
        self._tag = tag
        a = dict(attrs)
        if tag == "meta" and a.get("name", "").lower() == "description":
            self.desc = a.get("content", "")
        if tag in ("script", "style", "noscript"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._skip:
            return
        t = data.strip()
        if not t:
            return
        if self._tag == "title" and not self.title:
            self.title = t
        elif self._tag in ("h1", "h2", "h3") and len(self.headings) < 20:
            self.headings.append(t)
        elif len(" ".join(self._text)) < 4000:
            self._text.append(t)


def _norm(url: str) -> str:
    url = (url or "").strip()
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def research_site(url: str, *, timeout: float = 15.0) -> dict:
    url = _norm(url)
    out = {"url": url, "ok": False, "title": "", "description": "", "headings": [],
           "text": "", "socials": {}, "pages_seen": [], "error": ""}
    if not url:
        out["error"] = "no url"
        return out
    try:
        import httpx
        with httpx.Client(follow_redirects=True, timeout=timeout,
                          headers={"User-Agent": "SaathiAI-Research/1.0"}) as c:
            html = _fetch(c, url, out)
            if html is None:
                return out
            p = _Extract(); p.feed(html)
            out.update(ok=True, title=p.title, description=p.desc,
                       headings=p.headings, text=" ".join(p._text)[:3500])
            out["socials"] = _find_socials(html)
            # skim one more likely-informative page (about/services) for depth
            for path in ("about", "about-us", "services"):
                link = _same_site_link(html, url, path)
                if link and link not in out["pages_seen"]:
                    extra = _fetch(c, link, out, record=True)
                    if extra:
                        p2 = _Extract(); p2.feed(extra)
                        out["headings"] += [h for h in p2.headings if h not in out["headings"]][:6]
                        out["text"] = (out["text"] + " " + " ".join(p2._text))[:5000]
                        for k, v in _find_socials(extra).items():
                            out["socials"].setdefault(k, v)
                    break
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"[:160]
    return out


def _fetch(client, url, out, record=False) -> str | None:
    try:
        r = client.get(url)
        if record:
            out["pages_seen"].append(url)
        if r.status_code >= 400 or "text/html" not in r.headers.get("content-type", ""):
            if not record:
                out["error"] = f"HTTP {r.status_code}"
            return None
        return r.text
    except Exception as e:
        if not record:
            out["error"] = f"{type(e).__name__}: {e}"[:120]
        return None


def _find_socials(html: str) -> dict:
    found = {}
    for name, pat in _SOCIALS.items():
        m = re.search(pat, html, re.I)
        if m:
            u = m.group(0).rstrip("\"'>).,")
            if not any(x in u for x in ("sharer", "share?", "intent", "/plugins")):
                found[name] = "https://" + u if not u.startswith("http") else u
    return found


def _same_site_link(html: str, base: str, keyword: str) -> str | None:
    host = urlparse(base).netloc
    for m in re.finditer(r'href=["\']([^"\']+)["\']', html, re.I):
        href = m.group(1)
        if keyword in href.lower():
            full = urljoin(base, href)
            if urlparse(full).netloc in ("", host):
                return full
    return None


def summarize(site: dict) -> str:
    """One text block for the research prompt."""
    if not site.get("ok"):
        return f"[Website {site.get('url','')} could not be crawled: {site.get('error','')}]"
    parts = [f"WEBSITE {site['url']}",
             f"Title: {site.get('title','')}",
             f"Meta: {site.get('description','')}",
             f"Headings: {' | '.join(site.get('headings', [])[:12])}",
             f"Content: {site.get('text','')[:1800]}"]
    if site.get("socials"):
        parts.append("Social profiles found: " + ", ".join(f"{k}={v}" for k, v in site["socials"].items()))
    return "\n".join(parts)
