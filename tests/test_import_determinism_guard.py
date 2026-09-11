"""Tests for the repository-root `saathi` import guard.

The guard itself runs at collection time in the root ``conftest.py``. These
tests cover its decision function directly so the failure path is exercised
without needing a second interpreter or a real cross-worktree install.
"""
from __future__ import annotations

import importlib.util
import pathlib
import types

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFTEST = REPO_ROOT / "conftest.py"


def _load_conftest_module() -> types.ModuleType:
    """Import the root conftest under a private name, without re-running pytest."""
    spec = importlib.util.spec_from_file_location("_saathi_root_conftest", CONFTEST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestGuardIsWiredUp:
    def test_root_conftest_exists(self):
        assert CONFTEST.is_file(), "root conftest.py is the guard's only host"

    def test_repo_root_is_this_checkout(self):
        mod = _load_conftest_module()
        assert mod.REPO_ROOT == REPO_ROOT


class TestGuardAcceptsLocalPackage:
    def test_live_saathi_resolves_inside_this_repository(self):
        import saathi

        resolved = pathlib.Path(saathi.__file__).resolve()
        # Raises ValueError if `saathi` came from another checkout.
        relative = resolved.relative_to(REPO_ROOT)
        assert relative.parts[0] == "saathi"

    def test_guard_passes_for_the_current_session(self):
        mod = _load_conftest_module()
        mod._assert_saathi_is_local()  # must not raise


class TestGuardRejectsForeignPackage:
    def test_raises_when_saathi_comes_from_another_worktree(self, monkeypatch):
        mod = _load_conftest_module()
        foreign = types.SimpleNamespace(
            __file__="/Users/someone/SaathiAI-other-worktree/saathi/__init__.py"
        )
        monkeypatch.setitem(__import__("sys").modules, "saathi", foreign)

        with pytest.raises(RuntimeError) as exc:
            mod._assert_saathi_is_local()

        message = str(exc.value)
        assert "SAATHI_IMPORT_GUARD" in message
        assert "SaathiAI-other-worktree" in message, "must name the wrong path"
        assert str(REPO_ROOT) in message, "must name the expected path"
        assert "pip uninstall saathiai" in message, "must state the remedy"

    def test_raises_for_namespace_package_without_file(self, monkeypatch):
        mod = _load_conftest_module()
        foreign = types.SimpleNamespace()  # no __file__
        monkeypatch.setitem(__import__("sys").modules, "saathi", foreign)

        with pytest.raises(RuntimeError) as exc:
            mod._assert_saathi_is_local()

        assert "SAATHI_IMPORT_GUARD" in str(exc.value)


class TestGuardIsCheap:
    def test_guard_does_no_io_beyond_path_resolution(self):
        """The guard must stay import-time cheap on an 8 GB host.

        It may only touch `saathi.__file__` and resolve paths — no filesystem
        walk, no subprocess, no network.
        """
        source = CONFTEST.read_text(encoding="utf-8")
        for forbidden in ("subprocess", "socket", "requests", "urllib", "glob(", "rglob("):
            assert forbidden not in source, f"guard must not use {forbidden}"
