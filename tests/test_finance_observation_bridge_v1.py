"""M — FINANCIAL_BROWSER_RUNTIME_OBSERVATION_BRIDGE tests.

Proves a local authenticated consumer can request NORMALIZED observations from the process
that owns the Financial Browser runtime — with zero browser control, zero raw DOM/HTML/
cookies/tokens/screenshots crossing the bridge, and full Saathi Read / auth / provider /
domain / sensitive-page gating. Includes the critical process-boundary proof (Phase 29) and
a real-headless-browser read (Phase 30). No credentials, no trading.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

from saathi.platform.finance.browser_runtime import (
    FinancialBrowserRuntimeManager, RuntimeState,
)
from saathi.platform.finance.observation_bridge import (
    FinancialBrowserObservationService, S_DOMAIN_OUT_OF_SCOPE, S_LOGIN_REQUIRED,
    S_NO_RUNTIME, S_OK, S_PROVIDER_MISMATCH, S_READ_OFF, S_REAUTH_REQUIRED,
    S_SENSITIVE_BLOCKED, S_STRUCTURE_NOT_AUTHORIZED,
)
from saathi.platform.finance.policy import Provider

sys.path.insert(0, os.path.dirname(__file__))
from _bridge_fakes import seed_fake_runtime  # noqa: E402

HERE = os.path.dirname(__file__)
ROOT = os.path.dirname(HERE)
TMS_URL = "https://nepsetms.com.np/tms/me/memberclientholding"
ROWS = [{"symbol": "NABIL", "quantity": "100", "available": "100", "wacc": "500",
         "displayed_value": "55400"},
        {"symbol": "HDL", "quantity": "50", "available": "50", "wacc": "1100",
         "displayed_value": "60050"}]
OWNER_VALUES = ("NABIL", "HDL", "55400", "60050", "OWNER NAME", "12345")


def _svc(**kw):
    m = FinancialBrowserRuntimeManager()
    rt = seed_fake_runtime(m, Provider.TMS, url=TMS_URL, rows=ROWS,
                           headers=["Symbol", "Qty", "Available", "WACC", "Value"], **kw)
    return FinancialBrowserObservationService(manager=m), m, rt


# 1 — happy path: normalized observation, holding_count, authorized view
def test_observe_portfolio_ok():
    svc, m, rt = _svc()
    env = svc.observe_portfolio("TMS")
    assert env["available"] and env["state"] == S_OK
    assert env["runtime_id"] == rt.runtime_id
    assert env["holding_count"] == 2
    assert env["view"] and len(env["view"]["positions"]) == 2
    assert env["freshness"] == "FRESH"


# 2 — status is safe metadata, no page read required
def test_status():
    svc, m, rt = _svc()
    st = svc.status("TMS")
    assert st["runtime_id"] == rt.runtime_id
    assert st["authentication_state"] == "OWNER_AUTHENTICATED"
    assert st["read_allowed"] is True
    assert "view" not in st and "structure" not in st


# 3 — Saathi Read gate
def test_read_off():
    svc, m, rt = _svc(read_on=False)
    env = svc.observe_portfolio("TMS")
    assert not env["available"] and env["state"] == S_READ_OFF


# 4 — login required
def test_login_required():
    svc, m, rt = _svc(authenticated=False)
    assert svc.observe_portfolio("TMS")["state"] == S_LOGIN_REQUIRED


# 5 — no runtime
def test_no_runtime():
    svc = FinancialBrowserObservationService(manager=FinancialBrowserRuntimeManager())
    assert svc.observe_portfolio("TMS")["state"] == S_NO_RUNTIME


# 6 — provider isolation: TMS runtime_id under BINANCE request → mismatch
def test_provider_mismatch():
    svc, m, rt = _svc()
    env = svc.observe_portfolio("BINANCE", runtime_id=rt.runtime_id)
    assert env["state"] == S_PROVIDER_MISMATCH


# 7 — domain revalidation
def test_domain_out_of_scope():
    m = FinancialBrowserRuntimeManager()
    seed_fake_runtime(m, Provider.TMS, url="https://evil.example.com/holdings", rows=ROWS)
    svc = FinancialBrowserObservationService(manager=m)
    assert svc.observe_portfolio("TMS")["state"] == S_DOMAIN_OUT_OF_SCOPE


# 8 — sensitive page blocked
def test_sensitive_page_blocked():
    m = FinancialBrowserRuntimeManager()
    seed_fake_runtime(m, Provider.TMS, url="https://nepsetms.com.np/tms/login", rows=ROWS)
    svc = FinancialBrowserObservationService(manager=m)
    assert svc.observe_portfolio("TMS")["state"] == S_SENSITIVE_BLOCKED


# 9 — session expiry
def test_expiry():
    svc, m, rt = _svc()
    rt.last_active_at = time.time() - 10_000
    rt.ttl_sec = 1800
    assert svc.observe_portfolio("TMS")["state"] == S_REAUTH_REQUIRED


# 10 — cache: second read served CACHED
def test_cache():
    svc, m, rt = _svc()
    a = svc.observe_portfolio("TMS")
    b = svc.observe_portfolio("TMS")
    assert a["freshness"] == "FRESH" and b["freshness"] == "CACHED"


# 11 — single-flight: concurrent reads collapse to one underlying observation
def test_single_flight(monkeypatch):
    svc, m, rt = _svc()
    calls = {"n": 0}
    import saathi.platform.finance.browser_portfolio as bp
    real = bp.read_portfolio

    def slow(runtime_id, **kw):
        calls["n"] += 1
        time.sleep(0.2)
        return real(runtime_id, **kw)

    monkeypatch.setattr(bp, "read_portfolio", slow)
    out = []
    threads = [threading.Thread(target=lambda: out.append(svc.observe_portfolio("TMS")))
               for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert calls["n"] == 1                      # one DOM traversal, many consumers
    assert all(o["available"] for o in out)


# 12 — kill switch invalidates cache
def test_kill_invalidation():
    svc, m, rt = _svc()
    svc.observe_portfolio("TMS")               # fill cache
    m.disable_saathi_read(rt.runtime_id)
    env = svc.observe_portfolio("TMS")
    assert env["state"] == S_READ_OFF
    assert "TMS" not in svc._cache


# 13 — close invalidates
def test_close_invalidation():
    svc, m, rt = _svc()
    svc.observe_portfolio("TMS")
    m.close(rt.runtime_id)
    svc.invalidate(Provider.TMS)
    assert svc.observe_portfolio("TMS")["state"] == S_NO_RUNTIME


# 14 — evidence projection: counts + field NAMES only, no owner values
def test_evidence_projection():
    svc, m, rt = _svc()
    ev = svc.evidence("TMS")
    assert ev["holding_count"] == 2 and ev["resolved_symbol_count"] == 2
    assert ev["schema_state"] == "PROVISIONAL"        # TMS selectors unverified
    assert "view" not in ev                            # authorized view NOT in evidence
    blob = json.dumps(ev)
    for v in ("55400", "60050"):                       # no owner quantities/values
        assert v not in blob


# 15 — structure requires explicit owner authorization
def test_structure_needs_authorization():
    svc, m, rt = _svc()
    assert svc.observe_structure("TMS")["state"] == S_STRUCTURE_NOT_AUTHORIZED


# 16 — structure exposes shape only, ZERO owner values (Phase 27)
def test_structure_sanitized():
    m = FinancialBrowserRuntimeManager()
    seed_fake_runtime(m, Provider.TMS, url=TMS_URL, rows=ROWS,
                      headers=["Client Name", "BOID", "Symbol", "Qty", "Value"])
    svc = FinancialBrowserObservationService(manager=m)
    env = svc.observe_structure("TMS", authorize_structure_inspection=True)
    assert env["available"] and env["state"] == S_OK
    st = env["structure"]
    assert st["has_table_or_grid"] and st["row_count"] == 2
    blob = json.dumps(st)
    for v in OWNER_VALUES:
        assert v not in blob                           # no owner cell values / names in structure


# 17 — service has NO browser-control / Playwright surface
def test_no_browser_control_surface():
    svc, m, rt = _svc()
    for banned in ("click", "type", "navigate", "goto", "fill", "press", "submit",
                   "evaluate", "download", "upload", "screenshot", "page", "context",
                   "browser", "dom", "html", "cookies"):
        assert not hasattr(svc, banned), banned


# 18 — normalized envelope carries no raw DOM/HTML/cookie/token/screenshot keys
def test_envelope_no_raw_channels():
    svc, m, rt = _svc()
    env = svc.observe_portfolio("TMS")
    blob = json.dumps(env).lower()
    for bad in ('"html"', '"outerhtml"', '"innerhtml"', '"cookie"', '"cookies"',
                '"token"', '"screenshot"', '"storage_state"', '"user_data_dir"'):
        assert bad not in blob


# ── Process-boundary proof (Phase 29) ───────────────────────────────────────────
BRIDGE_TOKEN = "bridge-test-token"


def _http(url, method="GET", body=None, timeout=5):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json", "x-saathi-token": BRIDGE_TOKEN})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode())


def _free_port():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture()
def bridge_server():
    port = _free_port()
    env = dict(os.environ, SAATHI_BRIDGE_PORT=str(port), SAATHI_BRIDGE_PROVIDER="TMS",
               SAATHI_BRIDGE_URL=TMS_URL, PYTHONPATH=ROOT, SAATHI_TOKEN=BRIDGE_TOKEN)
    proc = subprocess.Popen([sys.executable, os.path.join(HERE, "_bridge_boot.py")],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, cwd=ROOT)
    runtime_id = None
    base = f"http://127.0.0.1:{port}"
    try:
        # read seeded runtime_id, then poll until serving
        deadline = time.time() + 25
        while time.time() < deadline:
            line = proc.stdout.readline()
            if line.startswith("RUNTIME_ID="):
                runtime_id = line.strip().split("=", 1)[1]
                break
            if proc.poll() is not None:
                raise RuntimeError("boot process exited early")
        assert runtime_id
        while time.time() < deadline:
            try:
                st, _ = _http(f"{base}/api/v1/finance/browser/TMS/status")
                if st == 200:
                    break
            except (urllib.error.URLError, ConnectionError):
                time.sleep(0.3)
        yield base, runtime_id, proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


def test_process_boundary_observation(bridge_server):
    base, runtime_id, _ = bridge_server
    # 1) second process sees the SAME runtime_id across the boundary
    st, status = _http(f"{base}/api/v1/finance/browser/TMS/status")
    assert st == 200 and status["runtime_id"] == runtime_id

    # 2) second process receives a NORMALIZED observation (no Playwright access)
    st, env = _http(f"{base}/api/v1/finance/browser/TMS/observe-portfolio",
                    method="POST", body={})
    assert st == 200 and env["available"] and env["holding_count"] == 2
    assert env["view"]["positions"][0]["symbol"] in ("NABIL", "HDL")

    # 3) no raw browser channels crossed the boundary
    blob = json.dumps(env).lower()
    for bad in ("<html", "<tr", "outerhtml", "innerhtml", "document.cookie",
                "user_data_dir", "storage_state", "screenshot"):
        assert bad not in blob

    # 4) there is NO generic DOM/browser-control endpoint to reach the Page
    for bad_path in ("dom", "html", "evaluate", "click", "page"):
        try:
            code, _ = _http(f"{base}/api/v1/finance/browser/TMS/{bad_path}")
        except urllib.error.HTTPError as e:
            code = e.code
        assert code in (404, 405), (bad_path, code)

    # 5) evidence projection crosses without owner values
    st, ev = _http(f"{base}/api/v1/finance/browser/TMS/evidence")
    assert st == 200 and ev["holding_count"] == 2 and "view" not in ev

    # 6) close from the second process → observation no longer available
    _http(f"{base}/api/v1/finance/browser/close", method="POST",
          body={"runtime_id": runtime_id})
    st, env2 = _http(f"{base}/api/v1/finance/browser/TMS/observe-portfolio",
                     method="POST", body={})
    assert env2["state"] == S_NO_RUNTIME


# ── Real headless browser read (Phase 30) ───────────────────────────────────────
def test_real_headless_structure(tmp_path):
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        pytest.skip("playwright not importable")
    html = tmp_path / "holdings.html"
    html.write_text(
        "<html><body><table id='portfolioTable'><thead><tr>"
        "<th>Symbol</th><th>Qty</th></tr></thead><tbody>"
        "<tr><td>NABIL</td><td>100</td></tr>"
        "<tr><td>HDL</td><td>50</td></tr></tbody></table></body></html>")
    # conftest may override HOME; point Playwright at the real on-box browser cache
    for cand in ("/Users/macbookpro/Library/Caches/ms-playwright",
                 os.path.expanduser("~/Library/Caches/ms-playwright")):
        if os.path.isdir(cand):
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = cand
            break
    pw = None
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
    except Exception as e:
        if pw:
            pw.stop()
        pytest.skip(f"headless chromium unavailable: {e}")
    try:
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(f"file://{html}")
        m = FinancialBrowserRuntimeManager()
        rt = m.open(Provider.TMS, launch=False)
        rt.runtime_state = RuntimeState.OPEN_OWNER_CONTROL
        m.mark_owner_authenticated(rt.runtime_id)

        class _Ctx:
            pages = [page]
        m._pw[Provider.TMS] = (None, _Ctx())
        m.set_saathi_read(rt.runtime_id, True)
        svc = FinancialBrowserObservationService(manager=m)
        env = svc.observe_structure("TMS", authorize_structure_inspection=True)
        assert env["available"], env
        st = env["structure"]
        assert st["has_table_or_grid"] and st["row_count"] == 2
        # real DOM read, but only shape crossed — no owner values
        blob = json.dumps(st)
        assert "NABIL" not in blob and "100" not in blob
    finally:
        browser.close()
        pw.stop()
