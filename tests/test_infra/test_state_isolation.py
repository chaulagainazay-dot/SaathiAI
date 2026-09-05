"""TEST-INFRA-2 — invariants for test-state isolation.

These guard the two defects this milestone fixed, so neither can return
silently.
"""
from __future__ import annotations

import os
import pathlib
import tempfile

import pytest

from saathi.agentdev import config_protection as CP


# ── symlinked HOME must not bypass config protection ───────────────────────

def test_symlinked_home_still_protects_user_config(monkeypatch):
    """A symlinked $HOME must not turn ~/.claude/settings.json UNPROTECTED.

    macOS mkdtemp returns /var/... which symlinks to /private/var/....
    ``classify_path`` resolves the candidate; if ``_home()`` does not resolve
    too, ``relative_to`` raises and the path classifies as unprotected — an
    agent could then write the operator's Claude settings.
    """
    symlinked_home = tempfile.mkdtemp(prefix="saathi-symlink-home-")
    assert pathlib.Path(symlinked_home).resolve() != pathlib.Path(symlinked_home), (
        "this platform did not give a symlinked temp dir; the regression this "
        "test guards cannot be reproduced here"
    )
    monkeypatch.setenv("HOME", symlinked_home)

    verdict = CP.classify_path("~/.claude/settings.json")
    assert verdict.protected is True


def test_home_resolution_is_symlink_stable(monkeypatch):
    symlinked_home = tempfile.mkdtemp(prefix="saathi-symlink-home-")
    monkeypatch.setenv("HOME", symlinked_home)
    assert CP._home() == pathlib.Path(symlinked_home).resolve()


@pytest.mark.parametrize(
    "candidate",
    ["~/.claude/settings.json", "~/.claude/hooks.json", "~/.ssh/id_rsa", "~/.aws/credentials"],
)
def test_protected_surfaces_remain_protected_under_redirected_home(candidate):
    """The conftest redirects HOME for the whole session. Protection must hold."""
    assert CP.is_protected(candidate) is True


# ── the test session must not touch the operator's real state ──────────────

def test_home_is_redirected_for_the_test_session():
    home = pathlib.Path(os.path.expanduser("~")).resolve()
    assert "saathi-test-home-" in str(home), (
        f"HOME is {home}; the test session is using the real home directory and "
        "can mutate the operator's ~/.saathi stores"
    )


def test_home_is_not_the_real_user_home():
    home = pathlib.Path(os.path.expanduser("~")).resolve()
    assert home != pathlib.Path("/Users/macbookpro").resolve()
    assert not str(home).startswith("/Users/")


def test_evidence_root_is_redirected_for_the_test_session():
    root = os.environ.get("SAATHI_EVIDENCE_ROOT", "")
    assert "saathi-test-evidence-" in root, (
        f"SAATHI_EVIDENCE_ROOT is {root!r}; evidence writers will rewrite "
        "tracked files under docs/evidence/**"
    )


def test_evidence_root_is_seeded_with_the_committed_tree():
    """Gates read committed evidence, so isolation copies rather than starts blank."""
    root = pathlib.Path(os.environ["SAATHI_EVIDENCE_ROOT"])
    assert (root / "docs" / "evidence").is_dir()


def test_security_store_default_is_isolated():
    from saathi.security.store import SecurityStore

    store = SecurityStore()
    try:
        assert "/Users/macbookpro/.saathi" not in str(store.path)
    finally:
        store.close()
