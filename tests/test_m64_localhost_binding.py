"""M64 — the server default host must fail safe to loopback.

A bare run (no SAATHI_HOST) must bind 127.0.0.1, not 0.0.0.0. Deployments that
intentionally bind all interfaces set SAATHI_HOST explicitly (Dockerfile ENV);
the launcher sets 127.0.0.1. This locks the hardened default.
"""
from __future__ import annotations

import importlib
import os

import saathi.config as cfg


def test_default_host_is_loopback(monkeypatch):
    monkeypatch.delenv("SAATHI_HOST", raising=False)
    reloaded = importlib.reload(cfg)
    try:
        assert reloaded.HOST == "127.0.0.1"
        assert reloaded.HOST != "0.0.0.0"
    finally:
        importlib.reload(cfg)  # restore module state for other tests


def test_explicit_host_env_still_honored(monkeypatch):
    monkeypatch.setenv("SAATHI_HOST", "0.0.0.0")
    reloaded = importlib.reload(cfg)
    try:
        assert reloaded.HOST == "0.0.0.0"  # deploy override still works
    finally:
        monkeypatch.delenv("SAATHI_HOST", raising=False)
        importlib.reload(cfg)
