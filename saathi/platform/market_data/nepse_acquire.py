"""M — AUTOMATED_OFFICIAL_NEPSE_ARTIFACT_ACQUISITION.

Deterministic Playwright acquisition of the OFFICIAL NEPSE Today's-Price CSV via the
site's own visible "Download as CSV" control (PUBLIC_OFFICIAL_BROWSER_DOWNLOAD). The
downloaded FILE — not DOM text, not XHR JSON, not scraped cells — is the input to the
existing canonical importer. No token replay, no anti-bot bypass, no CAPTCHA solving, no
broker/TMS pages, no Browser Use, no Agent Reach. One browser worker; torn down after use.
Read + download only; the ONLY canonical write is via owner_import.run_import.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from saathi.browser.policy import check_domain
from saathi.platform.market_data.owner_import import ImportResult, ImportStatus, run_import
from saathi.platform.market_data.store import MarketDataStore

SOURCE_PAGE = "https://www.nepalstock.com/today-price"
ALLOWED_HOSTS = ("nepalstock.com",)
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_DOWNLOAD_SELECTOR = "i.fa-download"     # official "Download as CSV" control
ACQUIRE_DIR = Path.home() / ".saathi" / "nepse_artifacts"


class AcquisitionStatus(str, Enum):
    DOWNLOAD_AVAILABLE = "DOWNLOAD_AVAILABLE"
    NOT_YET_PUBLISHED = "NOT_YET_PUBLISHED"
    SITE_UNAVAILABLE = "SITE_UNAVAILABLE"
    ANTI_BOT_BLOCKED = "ANTI_BOT_BLOCKED"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    UNEXPECTED_DOWNLOAD_ORIGIN = "UNEXPECTED_DOWNLOAD_ORIGIN"
    PLAYWRIGHT_UNAVAILABLE = "PLAYWRIGHT_UNAVAILABLE"


@dataclass
class AcquisitionResult:
    status: AcquisitionStatus
    acquisition_id: str = ""
    source_url: str = ""
    source_page: str = SOURCE_PAGE
    download_url: str = ""
    retrieved_at: float = 0.0
    browser_engine: str = "chromium"
    download_filename: str = ""
    local_path: str = ""
    detected_format: str = ""
    file_size: int = 0
    sha256: str = ""
    source_authority: str = "NEPAL_STOCK_EXCHANGE"
    acquisition_method: str = "OFFICIAL_BROWSER_DOWNLOAD"
    provenance_status: str = ""
    duration_sec: float = 0.0
    limitations: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in (
            "acquisition_id", "source_page", "source_url", "download_url", "retrieved_at",
            "browser_engine", "download_filename", "local_path", "detected_format", "file_size",
            "sha256", "source_authority", "acquisition_method", "provenance_status",
            "duration_sec")} | {"status": self.status.value, "limitations": list(self.limitations)}


def _origin_ok(url: str) -> bool:
    # blob: downloads carry the originating page origin — accept only nepalstock.
    if url.startswith("blob:"):
        url = url[len("blob:"):]
    return check_domain(url, allowed_hosts=list(ALLOWED_HOSTS)).allowed or "nepalstock.com" in url


def acquire_today_price(*, dest_dir: Path | str | None = None, timeout_sec: float = 45.0) -> AcquisitionResult:
    """Governed one-shot Playwright acquisition of the official Today's-Price CSV."""
    t0 = time.time()
    dest = Path(dest_dir) if dest_dir else ACQUIRE_DIR
    dest.mkdir(parents=True, exist_ok=True)
    if not check_domain(SOURCE_PAGE, allowed_hosts=list(ALLOWED_HOSTS)).allowed:
        return AcquisitionResult(AcquisitionStatus.UNEXPECTED_DOWNLOAD_ORIGIN,
                                 limitations=["seed page failed domain policy"])
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return AcquisitionResult(AcquisitionStatus.PLAYWRIGHT_UNAVAILABLE,
                                 duration_sec=round(time.time() - t0, 3))
    browser = None
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True, args=["--disable-http2", "--no-sandbox"])
        ctx = browser.new_context(user_agent=_UA, accept_downloads=True)
        page = ctx.new_page()
        page.goto(SOURCE_PAGE, wait_until="domcontentloaded", timeout=int(timeout_sec * 1000))
        page.wait_for_timeout(6000)
        loc = page.locator(_DOWNLOAD_SELECTOR).first
        if loc.count() == 0:
            return AcquisitionResult(AcquisitionStatus.NOT_YET_PUBLISHED,
                                     limitations=["no download control found (export not published?)"],
                                     duration_sec=round(time.time() - t0, 3))
        try:
            with page.expect_download(timeout=20000) as di:
                loc.click(timeout=6000)
            dl = di.value
        except Exception:
            return AcquisitionResult(AcquisitionStatus.DOWNLOAD_FAILED,
                                     limitations=["download event not received"],
                                     duration_sec=round(time.time() - t0, 3))
        if not _origin_ok(dl.url):
            return AcquisitionResult(AcquisitionStatus.UNEXPECTED_DOWNLOAD_ORIGIN,
                                     download_url=dl.url[:120],
                                     limitations=["download origin not official NEPSE"],
                                     duration_sec=round(time.time() - t0, 3))
        fn = dl.suggested_filename or f"nepse_today_{int(time.time())}.csv"
        acq_id = f"acq_{uuid.uuid4().hex[:12]}"
        local = dest / f"{acq_id}__{Path(fn).name}"
        dl.save_as(str(local))
        data = local.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        return AcquisitionResult(
            AcquisitionStatus.DOWNLOAD_AVAILABLE, acquisition_id=acq_id, source_url=SOURCE_PAGE,
            source_page=SOURCE_PAGE, download_url=dl.url[:120], retrieved_at=time.time(),
            download_filename=fn, local_path=str(local),
            detected_format="CSV" if fn.lower().endswith(".csv") else Path(fn).suffix.lstrip(".").upper(),
            file_size=len(data), sha256=sha, provenance_status="OFFICIAL_BROWSER_DOWNLOAD",
            duration_sec=round(time.time() - t0, 3))
    except Exception as e:
        msg = str(e).lower()
        st = (AcquisitionStatus.ANTI_BOT_BLOCKED if ("captcha" in msg or "403" in msg or "forbidden" in msg)
              else AcquisitionStatus.SITE_UNAVAILABLE)
        return AcquisitionResult(st, limitations=[f"{type(e).__name__}: {str(e)[:120]}"],
                                 duration_sec=round(time.time() - t0, 3))
    finally:
        try:
            if browser is not None:
                browser.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass


def acquire_and_import(*, store: MarketDataStore | None = None, dest_dir: Path | str | None = None,
                       acquirer=acquire_today_price) -> dict:
    """Acquire the official CSV, then canonically import via the existing importer.
    Never falls back to scraped/third-party prices on failure."""
    store = store or MarketDataStore()
    acq = acquirer(dest_dir=dest_dir)
    out = {"acquisition": acq.as_dict(), "import": None}
    if acq.status != AcquisitionStatus.DOWNLOAD_AVAILABLE:
        out["status"] = acq.status.value
        out["canonical_write"] = False
        return out
    res: ImportResult = run_import(acq.local_path, store=store, dry_run=False,
                                   acquisition_method="OFFICIAL_BROWSER_DOWNLOAD")
    out["import"] = res.as_dict()
    out["status"] = res.status.value
    out["canonical_write"] = res.status in (ImportStatus.IMPORTED,)
    return out


def acquisition_health(store: MarketDataStore | None = None) -> dict:
    from saathi.platform.market_data.owner_import import import_health
    store = store or MarketDataStore()
    h = import_health(store)
    h["source_kind"] = "AUTOMATED_OFFICIAL_BROWSER_DOWNLOAD (not a live feed; daily EOD export)"
    h["acquisition_page"] = SOURCE_PAGE
    return h
