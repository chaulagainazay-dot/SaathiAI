"""M — NEPSE_DISCLOSURE_DOCUMENT_INGESTION — governed official-document ingestion.

Fetches the document URLs already captured by V3 (never re-scrapes), validates
MIME + signature, hashes, extracts PDF text deterministically (no LLM, no JS
execution), extracts bounded structured facts, and writes DOCUMENT evidence into
the EXISTING evidence store with two-level provenance (parent web fact + official
document). Reuses saathi.browser.policy for domain/SSRF/redirect governance and
the established pypdf reader. Read-only, evidence-only, WEB_INTELLIGENCE.
"""
from __future__ import annotations

import hashlib
import io
import time
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urljoin

from saathi.browser.policy import check_domain, detect_prompt_injection, origin_of
from saathi.browser_research.bs_date import Calendar, parse_date
from saathi.browser_research.records import ExtractedRecord, ExtractionMethod, SymbolResolution
from saathi.browser_research.tiers import SourceTier, classify_source, host_of

# Conservative bounds for an 8 GB host.
MAX_DOCUMENT_BYTES = 15 * 1024 * 1024
MAX_PAGES = 60
DOCUMENT_TIMEOUT = 30.0
MAX_DOCUMENTS_PER_MISSION = 8
MAX_TOTAL_DOCUMENT_BYTES = 60 * 1024 * 1024

ALLOWED_CONTENT_TYPES = ("application/pdf", "text/plain")
_PDF_MAGIC = b"%PDF-"
DOC_DEPARTMENT = "browser_research"
DOC_PROJECT = "nepse_document"


class DocumentStatus(str, Enum):
    DOCUMENT_OK = "DOCUMENT_OK"
    DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
    DOCUMENT_BLOCKED = "DOCUMENT_BLOCKED"
    DOCUMENT_TOO_LARGE = "DOCUMENT_TOO_LARGE"
    DOCUMENT_UNSUPPORTED_TYPE = "DOCUMENT_UNSUPPORTED_TYPE"
    DOCUMENT_TIMEOUT = "DOCUMENT_TIMEOUT"
    DOCUMENT_HASH_FAILED = "DOCUMENT_HASH_FAILED"
    DOCUMENT_PARSE_FAILED = "DOCUMENT_PARSE_FAILED"
    DOCUMENT_EMPTY = "DOCUMENT_EMPTY"
    DOCUMENT_ENCRYPTED = "DOCUMENT_ENCRYPTED"
    DOCUMENT_REDIRECT_BLOCKED = "DOCUMENT_REDIRECT_BLOCKED"
    DOCUMENT_CHANGED = "DOCUMENT_CHANGED"     # applied as a warning alongside OK


@dataclass(frozen=True)
class DocumentIngestionRequest:
    mission_id: str
    source_url: str
    parent_fact_ref: str = ""
    source_page: str = ""
    source_tier: SourceTier = SourceTier.TIER_1_OFFICIAL
    expected_issuer: str = ""
    expected_document_type: str = ""
    allowed_domains: tuple[str, ...] = ()
    max_bytes: int = MAX_DOCUMENT_BYTES
    timeout: float = DOCUMENT_TIMEOUT


@dataclass
class DocumentIngestionResult:
    status: DocumentStatus
    source_url: str
    final_url: str = ""
    content_type: str = ""
    byte_length: int = 0
    sha256: str = ""
    fetched_at: float = 0.0
    page_count: int = 0
    title: str = ""
    issuer: str = ""
    document_date_raw: str = ""
    document_date_normalized: float | None = None
    date_calendar: Calendar = Calendar.UNKNOWN
    extracted_text_len: int = 0
    structured_facts: list = field(default_factory=list)   # ExtractedRecord
    injection_markers: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    evidence_refs: list = field(default_factory=list)
    parent_fact_ref: str = ""

    def as_dict(self) -> dict:
        return {
            "status": self.status.value, "source_url": self.source_url,
            "final_url": self.final_url, "content_type": self.content_type,
            "byte_length": self.byte_length, "sha256": self.sha256,
            "page_count": self.page_count, "title": self.title, "issuer": self.issuer,
            "document_date_raw": self.document_date_raw,
            "document_date_normalized": self.document_date_normalized,
            "date_calendar": self.date_calendar.value,
            "extracted_text_len": self.extracted_text_len,
            "structured_fact_count": len(self.structured_facts),
            "injection_markers": list(self.injection_markers),
            "warnings": list(self.warnings), "evidence_refs": list(self.evidence_refs),
            "parent_fact_ref": self.parent_fact_ref,
        }


# ── governed fetch (manual redirects, revalidated) ───────────────────────────
def governed_fetch(url: str, *, allowed_hosts, max_bytes: int, timeout: float):
    """Return (status, body_bytes|None, content_type, final_url). Never raises."""
    import httpx
    dom = check_domain(url, allowed_hosts=list(allowed_hosts))
    if not dom.allowed:
        return DocumentStatus.DOCUMENT_BLOCKED, None, "", url
    ua = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    cur = url
    try:
        with httpx.Client(follow_redirects=False, timeout=timeout,
                          headers={"User-Agent": ua, "Accept": "application/pdf,*/*"}) as c:
            for _ in range(6):
                r = c.get(cur)
                if r.status_code in (301, 302, 303, 307, 308):
                    loc = r.headers.get("location", "")
                    nxt = urljoin(cur, loc)
                    d = check_domain(nxt, allowed_hosts=list(allowed_hosts))
                    if not d.allowed:
                        return DocumentStatus.DOCUMENT_REDIRECT_BLOCKED, None, "", nxt
                    cur = nxt
                    continue
                if r.status_code == 404:
                    return DocumentStatus.DOCUMENT_NOT_FOUND, None, "", cur
                if r.status_code != 200:
                    return DocumentStatus.DOCUMENT_NOT_FOUND, None, "", cur
                body = r.content
                if len(body) > max_bytes:
                    return DocumentStatus.DOCUMENT_TOO_LARGE, None, r.headers.get("content-type", ""), cur
                return DocumentStatus.DOCUMENT_OK, body, r.headers.get("content-type", "").split(";")[0].strip().lower(), str(r.url)
            return DocumentStatus.DOCUMENT_REDIRECT_BLOCKED, None, "", cur
    except httpx.TimeoutException:
        return DocumentStatus.DOCUMENT_TIMEOUT, None, "", cur
    except Exception:
        return DocumentStatus.DOCUMENT_NOT_FOUND, None, "", cur


def _validate_type(content_type: str, body: bytes) -> tuple[bool, str]:
    """MIME + signature. Extension is never trusted."""
    ct = (content_type or "").lower()
    is_pdf_sig = body[:5] == _PDF_MAGIC
    if is_pdf_sig:
        return True, "application/pdf"
    if ct == "application/pdf" and not is_pdf_sig:
        return False, "pdf_mime_without_signature"   # fake .pdf / spoofed MIME
    if ct == "text/plain":
        return True, "text/plain"
    if ct not in ALLOWED_CONTENT_TYPES:
        return False, ct or "unknown"
    return False, ct or "unknown"


def _extract_pdf(body: bytes) -> tuple[str, int, str, list[str]]:
    """(text, page_count, title, warnings). Lazy pypdf; never executes JS."""
    warnings: list[str] = []
    try:
        from pypdf import PdfReader
    except Exception:
        return "", 0, "", ["pypdf_unavailable"]
    try:
        reader = PdfReader(io.BytesIO(body))
    except Exception:
        return "", 0, "", ["pdf_malformed"]
    if getattr(reader, "is_encrypted", False):
        try:
            if reader.decrypt("") == 0:      # empty-password decrypt failed
                return "", 0, "", ["pdf_encrypted"]
        except Exception:
            return "", 0, "", ["pdf_encrypted"]
    title = ""
    try:
        title = (reader.metadata.title or "") if reader.metadata else ""
    except Exception:
        title = ""
    pages = reader.pages[:MAX_PAGES]
    if len(reader.pages) > MAX_PAGES:
        warnings.append(f"page_cap:{MAX_PAGES}")
    texts = []
    for p in pages:
        try:
            texts.append(p.extract_text() or "")
        except Exception:
            texts.append("")
    return "\n".join(texts).strip(), len(reader.pages), str(title or ""), warnings


def _structured_from_text(text: str, *, url: str, tier: SourceTier,
                          security_index=None) -> list[ExtractedRecord]:
    from saathi.browser_research.extractors import _route, _resolve_symbol
    host = host_of(url)
    out: list[ExtractedRecord] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if len(line) < 10 or len(line) > 240:
            continue
        group = _route(line.lower())
        if group is None:
            continue
        key = line.lower()[:120]
        if key in seen:
            continue
        seen.add(key)
        dres = parse_date(line)
        if security_index is not None and getattr(security_index, "by_symbol", None):
            sym, sres = security_index.resolve(line)
        else:
            sym, sres = _resolve_symbol(line)
        out.append(ExtractedRecord(
            title=line[:240], category=group, source_url=url, source_host=host,
            source_tier=tier, extraction_method=ExtractionMethod.DOCUMENT_LINK,
            published_at_raw=dres.raw if dres.calendar != Calendar.UNKNOWN else "",
            published_at_normalized=dres.ad_ts, date_calendar=dres.calendar,
            symbol=sym, symbol_resolution=sres, summary=line[:240], confidence=0.75,
        ))
        if len(out) >= 40:
            break
    return out


def _prior_hashes_for_url(store, url: str) -> set[str]:
    try:
        rows = store.query(department=DOC_DEPARTMENT, project=DOC_PROJECT, limit=300)
    except Exception:
        return set()
    return {r.get("metrics", {}).get("sha256", "")
            for r in rows if r.get("metrics", {}).get("source_url") == url and r.get("metrics", {}).get("sha256")}


def _find_document_date(text: str):
    for line in text.splitlines()[:60]:
        dr = parse_date(line)
        if dr.calendar in (Calendar.AD, Calendar.BS):
            return dr
    return parse_date("")


def ingest_document(request: DocumentIngestionRequest, *, fetcher=governed_fetch,
                    security_index=None, store=None) -> DocumentIngestionResult:
    """Fetch → validate → hash → parse → structured facts → evidence. Never raises."""
    from saathi.evidence.schema import Evidence
    from saathi.evidence.store import default_store
    st = store or default_store()

    allowed = tuple(request.allowed_domains) or (host_of(request.source_url),)
    res = DocumentIngestionResult(status=DocumentStatus.DOCUMENT_OK,
                                  source_url=request.source_url,
                                  parent_fact_ref=request.parent_fact_ref,
                                  fetched_at=time.time())

    status, body, ct, final = fetcher(request.source_url, allowed_hosts=allowed,
                                      max_bytes=request.max_bytes, timeout=request.timeout)
    res.status, res.final_url, res.content_type = status, final, ct
    if status != DocumentStatus.DOCUMENT_OK or body is None:
        res.warnings.append(status.value)
        return res

    ok, label = _validate_type(ct, body)
    res.content_type = label
    if not ok:
        res.status = DocumentStatus.DOCUMENT_UNSUPPORTED_TYPE
        res.warnings.append(f"type:{label}")
        return res

    try:
        res.sha256 = hashlib.sha256(body).hexdigest()
    except Exception:
        res.status = DocumentStatus.DOCUMENT_HASH_FAILED
        return res
    res.byte_length = len(body)

    if label == "application/pdf":
        text, pages, title, warn = _extract_pdf(body)
        res.page_count, res.title, res.warnings = pages, title, list(warn)
        if "pdf_encrypted" in warn:
            res.status = DocumentStatus.DOCUMENT_ENCRYPTED
        elif "pdf_malformed" in warn:
            res.status = DocumentStatus.DOCUMENT_PARSE_FAILED
    else:
        text = body.decode("utf-8", errors="replace")
        res.page_count = 1
    res.extracted_text_len = len(text)
    if res.status == DocumentStatus.DOCUMENT_OK and not text.strip():
        res.status = DocumentStatus.DOCUMENT_EMPTY

    # document content is DATA — injection markers recorded, never executed
    res.injection_markers = detect_prompt_injection(text)

    dr = _find_document_date(text)
    res.document_date_raw = dr.raw
    res.document_date_normalized = dr.ad_ts
    res.date_calendar = dr.calendar

    if text.strip():
        res.structured_facts = _structured_from_text(
            text, url=request.source_url, tier=request.source_tier,
            security_index=security_index)

    # change / duplicate detection by SHA-256 per URL
    prior = _prior_hashes_for_url(st, request.source_url)
    is_duplicate = res.sha256 in prior
    if prior and not is_duplicate:
        res.warnings.append(DocumentStatus.DOCUMENT_CHANGED.value)

    # write ONE document evidence row (preserves two-level provenance)
    ev = Evidence(
        department=DOC_DEPARTMENT, project=DOC_PROJECT, episode=res.sha256 or "nohash",
        run=request.mission_id, director="document", provider="httpx", model="pypdf",
        confidence=0.9 if res.status == DocumentStatus.DOCUMENT_OK else 0.3,
        status=res.status.value,
        metrics={
            "source_url": request.source_url, "final_url": res.final_url,
            "content_type": res.content_type, "byte_length": res.byte_length,
            "sha256": res.sha256, "page_count": res.page_count, "title": res.title,
            "issuer": request.expected_issuer, "document_date_raw": res.document_date_raw,
            "document_date_normalized": res.document_date_normalized,
            "date_calendar": res.date_calendar.value,
            "parent_fact_ref": request.parent_fact_ref, "source_page": request.source_page,
            "source_tier": request.source_tier.name,
            "extracted_text_len": res.extracted_text_len,
            "structured_fact_count": len(res.structured_facts),
            "injection_markers": res.injection_markers,
            "duplicate": is_duplicate, "provenance": "BROWSER_DERIVED",
            "data_domain": "WEB_INTELLIGENCE",
            "text_preview": text.strip()[:400],
        },
        artifacts={"has_text": bool(text.strip()), "document_url": res.final_url},
    )
    try:
        res.evidence_refs.append(st.record(ev))
    except Exception:
        res.warnings.append("evidence_write_failed")
    return res


def browser_document_fetcher(captured_documents: dict, *, allowed_hosts=("nepalstock.com",)):
    """A governed_fetch-compatible fetcher sourcing bytes captured IN-SESSION by the
    governed Playwright browser (its own token; no forgery). Still domain-checked."""
    def fetch(url, *, allowed_hosts=allowed_hosts, max_bytes, timeout):
        if not check_domain(url, allowed_hosts=list(allowed_hosts)).allowed:
            return DocumentStatus.DOCUMENT_BLOCKED, None, "", url
        d = (captured_documents or {}).get(url)
        if not d:
            return DocumentStatus.DOCUMENT_NOT_FOUND, None, "", url
        if d.get("too_large"):
            return DocumentStatus.DOCUMENT_TOO_LARGE, None, d.get("content_type", ""), url
        body = d.get("body")
        st = d.get("status", 0)
        if body is None or st != 200:
            return DocumentStatus.DOCUMENT_NOT_FOUND, None, d.get("content_type", ""), url
        if len(body) > max_bytes:
            return DocumentStatus.DOCUMENT_TOO_LARGE, None, d.get("content_type", ""), url
        return DocumentStatus.DOCUMENT_OK, body, (d.get("content_type", "") or "").split(";")[0].strip().lower(), url
    return fetch
