"""``SAATHI_STATE_ROOT`` resolver contract.

Covers the precedence rule the isolation repair depends on: an explicit argument
beats a store-specific variable, which beats the canonical root, which beats the
historical ``~/.saathi`` default.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

from saathi.runtime_paths import (
    STATE_ROOT_ENV,
    StateRootError,
    state_path,
    state_root,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def no_root(monkeypatch):
    monkeypatch.delenv(STATE_ROOT_ENV, raising=False)


@pytest.fixture
def iso_root(tmp_path, monkeypatch):
    root = tmp_path / "isolated"
    monkeypatch.setenv(STATE_ROOT_ENV, str(root))
    return root


# ── 1. historical default ────────────────────────────────────────────────────
def test_unset_returns_historical_default(no_root):
    assert state_root() == pathlib.Path.home() / ".saathi"
    assert state_path("evidence.db") == pathlib.Path.home() / ".saathi" / "evidence.db"


# ── 2. absolute override ─────────────────────────────────────────────────────
def test_absolute_override_returns_isolated_root(iso_root):
    assert state_root() == iso_root
    assert state_path("evidence.db") == iso_root / "evidence.db"


# ── 3. blank override — documented as "treated as unset" ─────────────────────
@pytest.mark.parametrize("blank", ["", "   ", "\t", "\n"])
def test_blank_override_is_treated_as_unset(monkeypatch, blank):
    """Matches ``runtime_state_dir``'s handling of a cleared variable."""
    monkeypatch.setenv(STATE_ROOT_ENV, blank)
    assert state_root() == pathlib.Path.home() / ".saathi"


# ── 4. relative override is rejected ─────────────────────────────────────────
@pytest.mark.parametrize("bad", ["relative/dir", ".", "..", "./iso", "iso"])
def test_relative_override_is_rejected(monkeypatch, bad):
    monkeypatch.setenv(STATE_ROOT_ENV, bad)
    with pytest.raises(StateRootError):
        state_root()


def test_relative_override_error_is_bounded(monkeypatch):
    """The message must not echo the whole value back into a log."""
    monkeypatch.setenv(STATE_ROOT_ENV, "sneaky/" + "x" * 5000)
    with pytest.raises(StateRootError) as excinfo:
        state_root()
    assert len(str(excinfo.value)) < 200
    assert "xxxx" not in str(excinfo.value)


# ── 7/8. laziness and import purity ──────────────────────────────────────────
def test_resolution_is_lazy_not_frozen_at_import(tmp_path, monkeypatch):
    """Same already-imported module, two roots, two answers."""
    monkeypatch.setenv(STATE_ROOT_ENV, str(tmp_path / "a"))
    first = state_path("evidence.db")
    monkeypatch.setenv(STATE_ROOT_ENV, str(tmp_path / "b"))
    second = state_path("evidence.db")
    assert first != second
    assert first.parent == tmp_path / "a"
    assert second.parent == tmp_path / "b"


def test_importing_the_resolver_creates_nothing(tmp_path):
    """Import must not touch the filesystem, even with a root configured."""
    root = tmp_path / "untouched"
    env = {**os.environ, STATE_ROOT_ENV: str(root), "PYTHONDONTWRITEBYTECODE": "1"}
    code = (
        "import saathi.runtime_paths as rp;"
        "print(rp.state_root());"
        "print(rp.state_path('evidence.db'))"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, env=env,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert str(root) in out.stdout
    assert not root.exists(), "importing the resolver created the state root"


def test_resolver_functions_do_not_create_directories(iso_root):
    state_root()
    state_path("evidence.db")
    state_path("codebase_memory")
    assert not iso_root.exists(), "resolving a path must not create it"


# ── 9. two roots never share a resolved path ─────────────────────────────────
def test_distinct_roots_never_share_a_resolved_path(tmp_path, monkeypatch):
    names = ["evidence.db", "accounts.db", ".connector_key", "codebase_memory"]
    monkeypatch.setenv(STATE_ROOT_ENV, str(tmp_path / "one"))
    first = {n: state_path(n) for n in names}
    monkeypatch.setenv(STATE_ROOT_ENV, str(tmp_path / "two"))
    second = {n: state_path(n) for n in names}
    assert set(first.values()).isdisjoint(second.values())


# ── normalisation ────────────────────────────────────────────────────────────
def test_override_is_normalised_without_resolving_symlinks(tmp_path, monkeypatch):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    monkeypatch.setenv(STATE_ROOT_ENV, str(link / "sub" / ".." / "sub"))
    # `..` collapsed, but the symlink itself is preserved rather than dereferenced.
    assert state_root() == link / "sub"
    assert "link" in str(state_root())


def test_home_relative_override_is_expanded(monkeypatch):
    monkeypatch.setenv(STATE_ROOT_ENV, "~/iso-root")
    assert state_root() == pathlib.Path.home() / "iso-root"


# ── state_path() containment ─────────────────────────────────────────────────
@pytest.mark.parametrize("bad", ["../escape", "a/../../escape", ""])
def test_state_path_rejects_escapes_and_empty_names(iso_root, bad):
    with pytest.raises(StateRootError):
        state_path(bad)


def test_state_path_rejects_absolute_names(iso_root):
    with pytest.raises(StateRootError):
        state_path("/etc/passwd")


def test_state_path_accepts_nested_names(iso_root):
    assert state_path("stt-models/whisper-cpp") == iso_root / "stt-models" / "whisper-cpp"


def test_state_path_result_is_always_inside_the_root(iso_root):
    for name in ["evidence.db", "a/b/c.db", "codebase_memory"]:
        assert state_path(name).is_relative_to(iso_root)


# ── the personal root is never the answer under isolation ────────────────────
def test_isolated_root_never_resolves_into_the_personal_store(iso_root):
    personal = pathlib.Path.home() / ".saathi"
    for name in ["evidence.db", "security.db", ".connector_key", "reset_tokens.json"]:
        assert not state_path(name).is_relative_to(personal)
