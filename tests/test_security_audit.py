"""SECURITY-1 — egress/SSRF guard and external-text inertness."""
import pytest

from saathi.platform.research.evidence import EvidenceTrustClass
from saathi.platform.tg.security_audit import (
    ALLOWED_MARKET_DATA_HOSTS, assert_external_text_is_inert, audit, check_egress,
)


# ── allowed ──────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("url", [
    "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1d/x.zip",
    "https://api.binance.com/api/v3/klines?symbol=BTCUSDT",
    "https://stream.binance.com/ws/btcusdt@trade",
])
def test_public_market_data_hosts_allowed(url):
    assert check_egress(url).allowed is True


# ── SSRF / egress refusals ───────────────────────────────────────────────────────
@pytest.mark.parametrize("url,reason", [
    ("http://data.binance.vision/x", "SCHEME_NOT_HTTPS"),
    ("https://evil.example.com/x", "HOST_NOT_ALLOWLISTED"),
    ("https://127.0.0.1/x", "BLOCKED_IP_RANGE"),
    ("https://10.0.0.5/x", "BLOCKED_IP_RANGE"),
    ("https://192.168.1.1/x", "BLOCKED_IP_RANGE"),
    ("https://169.254.169.254/latest/meta-data/", "BLOCKED_IP_RANGE"),
    ("https://localhost/x", "BLOCKED_HOSTNAME"),
    ("https://metadata.google.internal/x", "BLOCKED_HOSTNAME"),
    ("file:///etc/passwd", "SCHEME_NOT_HTTPS"),
    ("ftp://data.binance.vision/x", "SCHEME_NOT_HTTPS"),
])
def test_ssrf_vectors_refused(url, reason):
    d = check_egress(url)
    assert d.allowed is False
    assert d.reason == reason


def test_credentials_in_url_refused():
    d = check_egress("https://user:pass@api.binance.com/api/v3/klines")
    assert d.allowed is False
    assert d.reason == "CREDENTIALS_IN_URL"


@pytest.mark.parametrize("path", [
    "/api/v3/order", "/api/v3/account", "/sapi/v1/capital/withdraw",
    "/fapi/v1/order", "/api/v3/userDataStream",
])
def test_private_endpoints_refused_even_on_allowed_host(path):
    d = check_egress(f"https://api.binance.com{path}")
    assert d.allowed is False
    assert d.reason == "PRIVATE_ENDPOINT_REFUSED"


def test_decision_is_falsy_when_blocked():
    assert not check_egress("https://evil.example.com/x")
    assert check_egress("https://api.binance.com/api/v3/ping")


# ── external text stays data ─────────────────────────────────────────────────────
class _Evidence:
    def __init__(self, trust, is_instruction):
        self.trust_class = trust
        self.is_instruction = is_instruction


def test_untrusted_external_text_is_inert():
    ev = _Evidence(EvidenceTrustClass.UNTRUSTED_EXTERNAL_DATA, False)
    assert assert_external_text_is_inert(ev) is True


def test_text_claiming_to_be_instruction_is_rejected():
    ev = _Evidence(EvidenceTrustClass.UNTRUSTED_EXTERNAL_DATA, True)
    assert assert_external_text_is_inert(ev) is False


# ── posture ──────────────────────────────────────────────────────────────────────
def test_audit_posture_denies_private_and_withdrawal():
    a = audit()
    assert a["private_account_access"] is False
    assert a["order_endpoints_reachable"] is False
    assert a["withdrawal_capable"] is False
    assert a["https_only"] is True
    assert a["external_text_is_instruction"] is False
    assert set(a["allowed_market_data_hosts"]) == set(ALLOWED_MARKET_DATA_HOSTS)
