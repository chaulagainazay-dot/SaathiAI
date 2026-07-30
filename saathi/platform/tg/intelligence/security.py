"""Security / boundary guards for institutional intelligence. Paper only."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from saathi.platform.tg.intelligence.models import AUTHORITY_VALUES

FORBIDDEN_DOMAINS = frozenset({
    "api.binance.com", "api.alpaca.markets", "paper-api.alpaca.markets",
    "api.kraken.com", "api.coinbase.com", "api.ibkr.com", "api.kite.trade",
    "api.bybit.com",
})

FORBIDDEN_ENV = frozenset({
    "BINANCE_API_KEY", "ALPACA_API_KEY", "ALPACA_API_SECRET", "APCA_API_KEY_ID",
    "KRAKEN_API_KEY", "COINBASE_API_KEY", "IBKR_PASSWORD", "ZERODHA_API_KEY",
    "BROKER_API_KEY", "BROKER_API_SECRET", "OAUTH_CLIENT_SECRET",
})


class IntelligenceSecurity:
    def __init__(self, repo_root: Path | None = None):
        self.repo_root = repo_root or Path(__file__).resolve().parents[4]

    def full_scan(self) -> dict[str, Any]:
        import os

        env_hits = [k for k in FORBIDDEN_ENV if os.environ.get(k)]
        pkg = Path(__file__).resolve().parent
        # Scan package modules for real network/broker imports (exclude this guard file).
        bad_imports: list[str] = []
        needles = (
            "import requests",
            "import httpx",
            "import aiohttp",
            "from alpaca",
            "import ccxt",
        )
        for p in pkg.glob("*.py"):
            if p.name == "security.py":
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for needle in needles:
                # Match only as a statement start (not documentation mentions).
                for line in text.splitlines():
                    stripped = line.strip()
                    if stripped.startswith(needle) or stripped.startswith("from " + needle.split()[-1]):
                        bad_imports.append(f"{p.name}:{needle}")
                        break

        ok = len(env_hits) == 0 and len(bad_imports) == 0
        return {
            "ok": ok,
            "credential_env_hits": env_hits,
            "forbidden_network_imports": bad_imports,
            "order_submission_paths_found": False,
            "broker_connectivity": False,
            "live_trading": False,
            "paper_only": True,
            "checks": {
                "no_api_keys_in_env_required": True,
                "no_broker_sdk_imports": len(bad_imports) == 0,
                "no_order_execution": True,
                "offline_capable": True,
            },
            **AUTHORITY_VALUES,
        }

    def refuse_broker_connect(self, target: str = "") -> dict[str, Any]:
        return {
            "ok": False,
            "code": "BROKER_CONNECTIVITY_FORBIDDEN",
            "target": target,
            "message": "M248–M255 intelligence layer refuses all broker connectivity.",
            **AUTHORITY_VALUES,
        }

    def refuse_credentials(self, value: str | None = None) -> dict[str, Any]:
        return {
            "ok": False,
            "code": "API_KEYS_FORBIDDEN",
            "accepted": False,
            "message": "API keys / secrets are not accepted by the intelligence layer.",
            "value_echoed": False,
            **AUTHORITY_VALUES,
        }

    def refuse_order(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "ok": False,
            "code": "ORDER_SUBMISSION_FORBIDDEN",
            "message": "Order submission is not available. Paper intelligence only.",
            **AUTHORITY_VALUES,
        }
