"""An application package must hash the same on every filesystem.

`AppRuntime.validate_package` compares the hash it computes over a package's
files against the `package_hash` pinned in that package's `app.json`. The walk
that produces it used raw `os.walk` order, which is readdir order and therefore
a property of the filesystem, not of the package. Every built-in package has two
hashed files, so there were two possible hashes: APFS yielded one order and ext4
the other, and a hash pinned on a macOS checkout failed validation on a Linux
runner with `package_hash_mismatch`.

These tests fail if the ordering guarantee is ever removed again.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from saathi.platform.apps import AppRuntime, reset_app_runtime_for_tests
from saathi.platform.apps.service import _packages_root
from saathi.platform.service import reset_platform_for_tests
from saathi.tool_runtime.registry import reset_registry_for_tests

PINNED_PACKAGES = ("platform_demo", "crm_lite", "erp_lite", "document_hub")


@pytest.fixture()
def env(tmp_path):
    reset_registry_for_tests()
    platform = reset_platform_for_tests(tmp_path / "hash.db")
    boot = platform.bootstrap_owner_secure(
        email="hash-owner@local",
        name="Hash Owner",
        password="HashOwnerPass1!",
    )
    ctx = platform.require_context(boot["token"])
    yield ctx, AppRuntime(platform)
    reset_app_runtime_for_tests(platform)
    reset_platform_for_tests()
    reset_registry_for_tests()


def _reversed_walk(monkeypatch):
    """Present every directory's entries in the opposite order."""
    real_walk = os.walk

    def walk(top, *args, **kwargs):
        for dirpath, dirnames, filenames in real_walk(top, *args, **kwargs):
            yield dirpath, list(reversed(dirnames)), list(reversed(filenames))

    monkeypatch.setattr("saathi.platform.apps.service.os.walk", walk)


@pytest.mark.parametrize("package_id", PINNED_PACKAGES)
def test_package_hash_is_independent_of_directory_read_order(
    env, monkeypatch, package_id
):
    ctx, svc = env
    forward = svc.validate_package(ctx, package_id=package_id)
    _reversed_walk(monkeypatch)
    backward = svc.validate_package(ctx, package_id=package_id)
    assert forward["package_hash"] == backward["package_hash"], (
        f"{package_id} hashes differently when the filesystem returns its "
        "entries in another order"
    )


@pytest.mark.parametrize("package_id", PINNED_PACKAGES)
def test_pinned_package_hash_validates_in_either_read_order(
    env, monkeypatch, package_id
):
    """The pinned hash must be reachable regardless of readdir order.

    This is the assertion that was failing on Linux CI: validation succeeded on
    the host the hash was pinned on and nowhere else.
    """
    ctx, svc = env
    _reversed_walk(monkeypatch)
    result = svc.validate_package(ctx, package_id=package_id)
    assert "package_hash_mismatch" not in result["errors"]
    assert result["ok"] is True, result["errors"]


def test_every_pinned_package_has_more_than_one_hashed_file():
    """Guards the guard.

    A package with fewer than two hashed files cannot expose an ordering bug, so
    the tests above would pass vacuously. If the built-in packages are ever
    reduced to a single file each, this fails and says why.
    """
    multi = []
    for package_id in PINNED_PACKAGES:
        pkg: Path = _packages_root() / package_id
        hashed = [p for p in pkg.iterdir() if p.is_file() and p.name != "app.json"]
        multi.append((package_id, len(hashed)))
    assert all(n >= 2 for _, n in multi), (
        "ordering is unobservable for these packages, so the determinism tests "
        f"prove nothing: {multi}"
    )
