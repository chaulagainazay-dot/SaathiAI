"""Loopback is not reachable from the governed browser by default.

A governed browser that may fetch 127.0.0.1 can read every service bound to this
machine — the SaathiOS API itself, Ollama, anything else listening — from a URL
that may have been chosen by untrusted page content. This was reachable in the
live local runtime: a fetch of http://127.0.0.1:8765/openapi.json succeeded.

Loopback stays available to a caller that grants it EXPLICITLY, which is how the
fixtures in this repository already work. The grant is what changed, not the
capability.
"""
from __future__ import annotations

import pytest

from saathi.browser.policy import DEFAULT_ALLOWED_HOST_SUFFIXES, check_domain

LOOPBACK_URLS = [
    "http://127.0.0.1:8765/openapi.json",   # the SaathiOS API itself
    "http://127.0.0.1:11434/api/tags",      # Ollama
    "http://localhost:8765/api/v1/mission",
    "http://localhost/",
    "http://[::1]:8765/",
    "http://127.0.0.1/",
]

PRIVATE_URLS = [
    "http://0.0.0.0:8765/",
    "http://169.254.169.254/latest/meta-data/",   # cloud metadata
    "http://metadata.google.internal/",
    "http://192.168.1.1/",
    "http://10.0.0.5/",
    "http://172.16.0.1/",
]


def test_loopback_is_not_in_the_default_allowlist():
    joined = " ".join(DEFAULT_ALLOWED_HOST_SUFFIXES).lower()
    for token in ("localhost", "127.0.0.1", "::1"):
        assert token not in joined, f"{token} is back in the default allowlist"


@pytest.mark.parametrize("url", LOOPBACK_URLS)
def test_loopback_is_denied_by_default(url):
    d = check_domain(url)
    assert not d.allowed, f"{url} was allowed by the default policy"


@pytest.mark.parametrize("url", PRIVATE_URLS)
def test_private_and_metadata_addresses_stay_denied(url):
    d = check_domain(url)
    assert not d.allowed, f"{url} was allowed"


def test_an_explicit_grant_still_reaches_loopback():
    """Fixtures must keep working; the grant simply has to be deliberate."""
    assert check_domain("http://127.0.0.1:9/", allowed_hosts=["127.0.0.1"]).allowed
    assert check_domain("http://localhost:9/", allowed_hosts=["localhost"]).allowed


def test_a_redirect_into_loopback_is_denied():
    """The allowlist is re-checked at the FINAL destination, not just the first."""
    from saathi.browser.policy import revalidate_redirect

    d = revalidate_redirect("https://example.com/start", "http://127.0.0.1:8765/openapi.json")
    assert not d.allowed
    assert "redirect_denied" in d.reason


def test_a_redirect_into_cloud_metadata_is_denied():
    from saathi.browser.policy import revalidate_redirect

    d = revalidate_redirect("https://example.com/start", "http://169.254.169.254/latest/meta-data/")
    assert not d.allowed


def test_the_public_allowlist_is_unchanged():
    """Tightening loopback must not have narrowed ordinary public access."""
    assert check_domain("https://example.com/x").allowed
    assert check_domain("https://sub.example.com/x").allowed
    # And an unrelated public host is still refused.
    assert not check_domain("https://evil.example.org.attacker.tld/").allowed


def test_protected_market_hosts_remain_denied_even_if_allowlisted():
    """The denylist outranks any grant — this is the anti-scraping invariant."""
    from saathi.browser.domain_policy import PROTECTED_MARKET_HOSTS

    for host in list(PROTECTED_MARKET_HOSTS)[:4]:
        d = check_domain(f"https://{host}/", allowed_hosts=[host])
        assert not d.allowed, f"{host} was reachable after an explicit grant"
