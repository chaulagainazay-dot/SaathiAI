"""M — Agent-Reach evaluation: bounded OPTIONAL web-research acquisition adapter.

Wraps the ALREADY-PRESENT Agent-Reach backends (Jina Reader webpage extraction +
web search) behind the FROZEN BrowserResearchProvider contract, feeding the
existing extractor/evidence/snapshot pipeline. It is a FALLBACK acquisition tier,
never the canonical NEPSE market-data source. READ-ONLY, WEB_INTELLIGENCE /
BROWSER_DERIVED. No gateway/Trading-Guardian/broker/portfolio/market_data writes.

The full `agent-reach` CLI is NOT required (and not installed here): Jina Reader is
`curl https://r.jina.ai/<url>` (no key, no install); search falls back to DDG.
Every target URL is revalidated against the existing domain/SSRF policy.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from saathi.browser.policy import check_domain, detect_prompt_injection
from saathi.browser_research.bs_date import Calendar, parse_date
from saathi.browser_research.contract import BrowserResearchProvider, FetchedPage
from saathi.browser_research.records import ExtractedRecord, ExtractionMethod, SymbolResolution
from saathi.browser_research.tiers import SourceTier, classify_source, host_of

AGENT_REACH_STATUS = "AGENT_REACH_PARTIAL"   # chat-tools wired; CLI absent; Jina/search functional


def agent_reach_available() -> dict:
    """Diagnostic: which Agent-Reach backends are actually usable (Phase 1/19)."""
    import shutil
    return {
        "agent_reach_cli": bool(shutil.which("agent-reach")),
        "jina_reader": bool(shutil.which("curl")),      # zero-install path
        "mcporter_exa": bool(shutil.which("mcporter")),
        "gh": bool(shutil.which("gh")),
        "yt_dlp": bool(shutil.which("yt-dlp")),
        "status": AGENT_REACH_STATUS,
    }


@dataclass
class AgentReachProvider(BrowserResearchProvider):
    """Fallback web-research provider over Agent-Reach's Jina/search backends."""
    allowed_hosts: tuple[str, ...] = ()
    max_pages: int = 6
    max_runtime_sec: float = 60.0
    reader: object = None      # injectable (url)->{"ok":bool,"output":str}; default internet_reach.read_webpage
    searcher: object = None    # injectable (query,n)->{"ok":bool,"output":str}
    _pages: int = field(default=0, init=False)
    _started: float = field(default_factory=time.time, init=False)
    _closed: bool = field(default=False, init=False)

    def _reader(self):
        if self.reader is not None:
            return self.reader
        from saathi.tools import internet_reach
        return internet_reach.read_webpage

    def _searcher(self):
        if self.searcher is not None:
            return self.searcher
        from saathi.tools import internet_reach
        return internet_reach.web_search

    @property
    def pages_fetched(self) -> int:
        return self._pages

    def fetch(self, url: str, *, mission_id: str, actor: str = "user:owner",
              selector: str = "", timeout: int = 25) -> FetchedPage:
        if self._closed:
            raise RuntimeError("provider closed")
        if self._pages >= self.max_pages:
            return FetchedPage(url=url, final_origin="", title="", content="",
                               status="blocked", error_category="max_pages_exceeded")
        if (time.time() - self._started) > self.max_runtime_sec:
            return FetchedPage(url=url, final_origin="", title="", content="",
                               status="blocked", error_category="max_runtime_exceeded")
        # Domain/SSRF policy on the REAL target (not the r.jina.ai proxy). With an
        # explicit allowlist → strict. Without one → allow any PUBLIC http(s) host
        # (research reads arbitrary public pages) but SSRF/private/scheme/metadata
        # are still blocked by check_domain BEFORE the allowlist stage.
        dom = check_domain(url, allowed_hosts=list(self.allowed_hosts) or None)
        if not dom.allowed and not (not self.allowed_hosts and dom.reason == "domain_not_allowlisted"):
            return FetchedPage(url=url, final_origin="", title="", content="",
                               status="denied", error_category=dom.reason)
        self._pages += 1
        try:
            res = self._reader()(url)
        except Exception as e:
            return FetchedPage(url=url, final_origin="", title="", content="",
                               status="failed", error_category=f"agent_reach_error:{type(e).__name__}")
        if not isinstance(res, dict) or not res.get("ok"):
            err = res.get("error", "no_output") if isinstance(res, dict) else "malformed_output"
            return FetchedPage(url=url, final_origin="", title="", content="",
                               status="failed", error_category=str(err)[:80])
        content = str(res.get("output") or "")
        host = host_of(url)
        return FetchedPage(url=url, final_origin=f"https://{host}", title="", content=content,
                           status="succeeded", injection_hits=tuple(detect_prompt_injection(content)),
                           retrieval_ts=time.time())

    def search(self, query: str, *, num_results: int = 5) -> dict:
        """Bounded web search. Snippets are context, NEVER confirmed facts."""
        try:
            res = self._searcher()(query, num_results)
        except Exception as e:
            return {"status": "degraded", "error": f"{type(e).__name__}", "results": []}
        if not isinstance(res, dict) or not res.get("ok"):
            return {"status": "degraded", "error": str((res or {}).get("error", ""))[:80], "results": []}
        return {"status": "ok", "method": ExtractionMethod.AGENT_REACH_SEARCH.value,
                "raw": str(res.get("output") or "")[:4000],
                "source": res.get("source", "exa/mcporter"),
                "retrieved_at": time.time()}

    def cleanup(self) -> dict:
        self._closed = True
        return {"closed": True, "driver": "AGENT_REACH", "pages_fetched": self._pages,
                "runtime_sec": round(time.time() - self._started, 3)}


def agent_reach_records(page: FetchedPage, *, now: float) -> list[ExtractedRecord]:
    """Normalize an Agent-Reach page into ExtractedRecords tagged JINA_READER."""
    from saathi.browser_research.extractors import _route, _resolve_symbol
    from saathi.browser_research.noise import is_noise
    import re as _re
    if not page.ok or not page.content:
        return []
    host = host_of(page.final_origin) or host_of(page.url)
    tier = classify_source(page.url)
    out: list[ExtractedRecord] = []
    seen: set[str] = set()
    for raw in page.content.splitlines():
        line = raw.strip().lstrip("#*->|").strip()
        # strip markdown links/images → keep the visible text, drop the URL noise
        line = _re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", line).strip()
        if len(line) < 10 or len(line) > 240 or is_noise(line):
            continue
        group = _route(line.lower())
        if group is None:
            continue
        if group in ("CORPORATE_ACTIONS", "COMPANY_EVENTS", "MARKET_CONTEXT") \
                and not any(c.isdigit() for c in line):
            continue
        key = line.lower()[:120]
        if key in seen:
            continue
        seen.add(key)
        dres = parse_date(line, calendar_hint="BS" if tier == SourceTier.TIER_1_OFFICIAL else None)
        sym, sres = _resolve_symbol(line)
        out.append(ExtractedRecord(
            title=line[:240], category=group, source_url=page.url, source_host=host,
            source_tier=tier, extraction_method=ExtractionMethod.JINA_READER,
            published_at_raw=dres.raw if dres.calendar != Calendar.UNKNOWN else "",
            published_at_normalized=dres.ad_ts, date_calendar=dres.calendar,
            symbol=sym, symbol_resolution=sres, summary=line[:240], confidence=0.6))
        if len(out) >= 40:
            break
    return out
