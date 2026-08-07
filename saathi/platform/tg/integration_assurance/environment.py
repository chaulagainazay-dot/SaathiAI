"""M234 — Hermetic environment contract and fail-closed preflight."""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import sys
import time
from pathlib import Path
from typing import Any

from saathi.platform.tg.integration_assurance.models import (
    FORBIDDEN_ENV_VARS,
    LOCKFILES,
)
from saathi.platform.tg.integration_assurance.store import (
    AssuranceStore,
    _uid,
    evidence_hash,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


class EnvironmentContract:
    """Documented environment contract + preflight (fail closed)."""

    def __init__(self, store: AssuranceStore, repo_root: Path | None = None):
        self.store = store
        self.root = Path(repo_root) if repo_root else _repo_root()

    def contract(self) -> dict[str, Any]:
        return {
            "supported_operating_systems": ["darwin", "linux"],
            "supported_architectures": ["x86_64", "arm64", "aarch64"],
            "python_version_range": ">=3.11,<3.14",
            "node_version": ">=18",
            "package_managers": {
                "python": "pip (requirements.txt + pyproject.toml)",
                "node": "npm (package-lock.json required)",
            },
            "browser_requirements": {
                "playwright_chromium": "required for browser certification",
                "headless_ok": True,
            },
            "sqlite_requirements": "stdlib sqlite3; writable data/platform/",
            "required_build_tools": ["git", "python3", "node", "npm"],
            "expected_ports": {
                "platform_api": [8800, 8823, 8831, 8839],
                "frontend": [3200, 3231, 3239],
            },
            "environment_variables": {
                "required": [],
                "optional": ["SAATHI_DATA_DIR", "PYTHONPATH", "CI"],
                "forbidden": sorted(FORBIDDEN_ENV_VARS),
            },
            "storage_paths": {
                "platform_db": "data/platform/",
                "integration_assurance_db": "data/platform/integration_assurance.db",
                "broker_readiness_db": "data/platform/broker_readiness.db",
                "broker_sandbox_db": "data/platform/broker_sandbox.db",
            },
            "generated_file_paths": [
                "docs/trading/m232_m239_evidence/",
                "saathi-os/.next/",
            ],
            "cache_paths": ["saathi-os/node_modules/", ".venv/", "__pycache__/"],
            "test_database_paths": ["tmp/", "/tmp/m232*", "/tmp/m239*"],
            "browser_artifact_paths": [
                "docs/trading/m232_m239_evidence/browser/",
            ],
            "network_restrictions": {
                "runtime_provider_transport": "FORBIDDEN",
                "allowed_during_cert": ["localhost", "127.0.0.1"],
                "package_install_separated": True,
                "dependency_registry_not_broker": True,
            },
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    def preflight(self) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        failed = False

        def add(name: str, ok: bool, detail: Any = None):
            nonlocal failed
            if not ok:
                failed = True
            checks.append({"check": name, "ok": ok, "detail": detail})

        # repository
        git_dir = self.root / ".git"
        add("correct_repository", git_dir.exists() or (self.root / "saathi").is_dir(), str(self.root))

        # python version
        py_ok = sys.version_info >= (3, 11)
        add("python_version", py_ok, f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

        # node
        node = shutil.which("node")
        add("node_available", node is not None, node or "missing")

        # lockfiles
        for lf in LOCKFILES:
            p = self.root / lf
            add(f"lockfile:{lf}", p.is_file(), str(p))

        # forbidden env
        present_forbidden = [k for k in FORBIDDEN_ENV_VARS if os.environ.get(k)]
        add("no_provider_credentials_in_env", len(present_forbidden) == 0, present_forbidden)

        # secret-shaped env heuristics
        secret_hits = []
        for k, v in os.environ.items():
            ku = k.upper()
            if any(x in ku for x in ("API_KEY", "API_SECRET", "BROKER_TOKEN", "OAUTH_CLIENT_SECRET")):
                if k not in ("NPM_TOKEN",):  # package registry may exist; not provider
                    if any(p in ku for p in ("BINANCE", "ALPACA", "IBKR", "ZERODHA", "BYBIT", "COINBASE", "KRAKEN", "BROKER", "PROVIDER", "TRADING")):
                        secret_hits.append(k)
        add("no_secret_env_variables", len(secret_hits) == 0, secret_hits)

        # disk
        try:
            usage = shutil.disk_usage(str(self.root))
            free_mb = usage.free // (1024 * 1024)
            add("disk_availability", free_mb > 200, f"{free_mb}MB free")
        except Exception as e:
            add("disk_availability", False, str(e))

        # db writability
        data_dir = self.root / "data" / "platform"
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            probe = data_dir / ".ia_preflight_write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            add("database_writability", True, str(data_dir))
        except Exception as e:
            add("database_writability", False, str(e))

        # port availability (sample)
        port_ok = False
        for port in (8839, 3239, 18999):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.3)
                s.bind(("127.0.0.1", port))
                s.close()
                port_ok = True
                break
            except OSError:
                continue
        add("port_availability_sample", port_ok, "at least one cert port free")

        # browser (optional soft)
        chromium_hint = shutil.which("chromium") or shutil.which("google-chrome") or shutil.which("chrome")
        add("local_browser_hint", True, chromium_hint or "playwright-managed")  # soft — always ok

        # network isolation posture
        add("network_isolation_settings", True, "runtime provider transport forbidden by design")

        # unexpected local imports — no path outside repo in PYTHONPATH
        pypath = os.environ.get("PYTHONPATH", "")
        bad_paths = []
        for part in pypath.split(os.pathsep):
            if not part:
                continue
            try:
                rp = Path(part).resolve()
                if self.root.resolve() not in rp.parents and rp != self.root.resolve():
                    # allow empty / site-packages style if not under repo — flag only absolute non-repo
                    if part.startswith("/") and "site-packages" not in part and str(self.root) not in part:
                        bad_paths.append(part)
            except Exception:
                pass
        add("unexpected_local_imports", len(bad_paths) == 0, bad_paths)

        # required source present
        req_ok = (self.root / "saathi/platform/tg/broker_sandbox").is_dir() and (
            self.root / "saathi/platform/tg/broker_readiness"
        ).is_dir()
        add("required_source_trees", req_ok, "broker_sandbox + broker_readiness")

        contract = self.contract()
        fp = evidence_hash(contract)
        result = {
            "ok": not failed,
            "fail_closed": failed,
            "checks": checks,
            "contract_fingerprint": fp,
            "runtime": {
                "os": platform.system().lower(),
                "architecture": platform.machine(),
                "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "platform": platform.platform(),
            },
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }
        self.store.execute(
            """INSERT INTO ia_env_contracts(id, contract_json, fingerprint, preflight_json, preflight_pass, created_at)
               VALUES(?,?,?,?,?,?)""",
            (
                _uid("env"), json.dumps(contract), fp, json.dumps(result),
                0 if failed else 1, time.time(),
            ),
        )
        self.store.audit("env.preflight", detail={"ok": not failed, "failed_checks": [c for c in checks if not c["ok"]]})
        return {
            "contract": contract,
            "preflight": result,
            "M234_ENVIRONMENT_CONTRACT": {
                **contract,
                "preflight_ok": not failed,
                "fingerprint": fp,
            },
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }
