"""Read-only observation engines — snapshots, quotes, history, metadata, status."""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.market_observation.errors import ObservationError
from saathi.platform.tg.market_observation.fixtures import (
    benchmark_fixture,
    corporate_actions_fixture,
    exchange_status_fixture,
    historical_bars_fixture,
    quote_fixture,
    symbol_metadata,
    symbol_universe,
)
from saathi.platform.tg.market_observation.models import (
    AUTHORITY_VALUES,
    DEFAULT_BENCHMARKS,
    DataFreshness,
    ObservationSource,
)
from saathi.platform.tg.market_observation.storage import ObservationStore, evidence_hash, _uid


class ObservationEngine:
    def __init__(self, store: ObservationStore):
        self.store = store
        self._seed_catalog()

    def _seed_catalog(self) -> None:
        now = time.time()
        for sym in symbol_universe():
            meta = symbol_metadata(sym)
            if not meta:
                continue
            existing = self.store.fetchone("SELECT symbol FROM mo_symbols WHERE symbol=?", (sym,))
            if existing:
                continue
            self.store.execute(
                "INSERT INTO mo_symbols(symbol, name, asset_class, exchange, currency, tick_size, lot_size, meta_json, updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    meta["symbol"], meta["name"], meta["asset_class"], meta["exchange"],
                    meta["currency"], meta["tick_size"], meta["lot_size"],
                    json.dumps({"source": meta["source"]}, sort_keys=True), now,
                ),
            )
        for ex in ("NYSE_ARCA", "NASDAQ", "CRYPTO_PAPER"):
            st = exchange_status_fixture(ex)
            self.store.execute(
                "INSERT OR REPLACE INTO mo_exchange_status(exchange, status, session, detail_json, updated_at) "
                "VALUES(?,?,?,?,?)",
                (st["exchange"], st["status"], st["session"],
                 json.dumps({"source": st["source"]}, sort_keys=True), now),
            )

    # ── Symbol metadata ──────────────────────────────────────────────────
    def list_symbols(self) -> dict[str, Any]:
        rows = self.store.fetchall("SELECT * FROM mo_symbols ORDER BY symbol")
        return {
            "ok": True,
            "count": len(rows),
            "symbols": rows,
            "read_only": True,
            **AUTHORITY_VALUES,
        }

    def get_symbol(self, symbol: str) -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM mo_symbols WHERE symbol=?", (symbol.upper(),))
        if not row:
            meta = symbol_metadata(symbol)
            if not meta:
                return {"ok": False, "code": "SYMBOL_NOT_FOUND", "symbol": symbol, **AUTHORITY_VALUES}
            return {"ok": True, **meta, **AUTHORITY_VALUES}
        return {"ok": True, **row, "read_only": True, **AUTHORITY_VALUES}

    # ── Quotes ───────────────────────────────────────────────────────────
    def get_quote(self, symbol: str, *, seed: int = 0, refresh: bool = False) -> dict[str, Any]:
        symbol = symbol.upper()
        if refresh:
            # Offline refresh only — regenerate from fixture, never authenticated live
            q = quote_fixture(symbol, seed=seed)
            if not q:
                raise ObservationError("SYMBOL_NOT_FOUND", symbol)
            qid = _uid("q")
            self.store.execute(
                "INSERT INTO mo_quotes(id, symbol, bid, ask, last, volume, source, freshness, observed_at, created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    qid, q["symbol"], q["bid"], q["ask"], q["last"], q["volume"],
                    q["source"], q["freshness"], q["observed_at"], time.time(),
                ),
            )
            self.store.audit("quote.refresh_offline", subject=symbol, detail={"source": q["source"]})
            return {"ok": True, "quote": q, "refreshed": True, **AUTHORITY_VALUES}

        row = self.store.fetchone(
            "SELECT * FROM mo_quotes WHERE symbol=? ORDER BY observed_at DESC LIMIT 1", (symbol,)
        )
        if row:
            return {"ok": True, "quote": row, "refreshed": False, **AUTHORITY_VALUES}
        # lazy load fixture
        return self.get_quote(symbol, seed=seed, refresh=True)

    def list_quotes(self, symbols: list[str] | None = None, *, seed: int = 0) -> dict[str, Any]:
        symbols = symbols or symbol_universe()
        quotes = []
        for s in symbols:
            r = self.get_quote(s, seed=seed)
            if r.get("ok"):
                quotes.append(r["quote"])
        return {"ok": True, "count": len(quotes), "quotes": quotes, "read_only": True, **AUTHORITY_VALUES}

    # ── Snapshots ────────────────────────────────────────────────────────
    def market_snapshot(self, *, label: str = "default", seed: int = 0) -> dict[str, Any]:
        quotes = self.list_quotes(seed=seed)
        exchanges = self.list_exchange_status()
        payload = {
            "label": label,
            "as_of": time.time(),
            "quotes": quotes.get("quotes"),
            "exchanges": exchanges.get("exchanges"),
            "source": ObservationSource.OFFLINE_FIXTURE.value,
            "authenticated": False,
            "read_only": True,
            "purpose": "validation_not_trading",
        }
        eh = evidence_hash(payload)
        sid = _uid("snap")
        self.store.execute(
            "INSERT INTO mo_snapshots(id, label, payload_json, source, evidence_hash, created_at) "
            "VALUES(?,?,?,?,?,?)",
            (sid, label, json.dumps(payload, sort_keys=True, default=str),
             ObservationSource.OFFLINE_FIXTURE.value, eh, time.time()),
        )
        self.store.audit("snapshot.created", subject=sid, detail={"label": label})
        return {"ok": True, "snapshot_id": sid, "evidence_hash": eh, **payload, **AUTHORITY_VALUES}

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM mo_snapshots WHERE id=?", (snapshot_id,))
        if not row:
            return {"ok": False, "code": "SNAPSHOT_NOT_FOUND", **AUTHORITY_VALUES}
        payload = json.loads(row["payload_json"])
        return {"ok": True, "snapshot_id": row["id"], "label": row["label"],
                "evidence_hash": row["evidence_hash"], **payload, **AUTHORITY_VALUES}

    # ── Historical refresh (offline) ─────────────────────────────────────
    def historical_refresh(self, symbol: str, *, n: int = 30, seed: int = 42) -> dict[str, Any]:
        symbol = symbol.upper()
        bars = historical_bars_fixture(symbol, n=n, seed=seed)
        if not bars:
            raise ObservationError("SYMBOL_NOT_FOUND", symbol)
        # replace bars for symbol
        self.store.execute("DELETE FROM mo_bars WHERE symbol=?", (symbol,))
        for b in bars:
            self.store.execute(
                "INSERT INTO mo_bars(id, symbol, ts, open, high, low, close, volume, source) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (_uid("bar"), b["symbol"], b["ts"], b["open"], b["high"], b["low"], b["close"],
                 b["volume"], b["source"]),
            )
        self.store.audit("history.refresh_offline", subject=symbol, detail={"n": n})
        return {
            "ok": True,
            "symbol": symbol,
            "bar_count": len(bars),
            "bars_sample": bars[:5] + ([{"truncated": True}] if len(bars) > 5 else []),
            "bars_tail": bars[-5:],
            "source": ObservationSource.OFFLINE_FIXTURE.value,
            "authenticated_live": False,
            "read_only": True,
            **AUTHORITY_VALUES,
        }

    def get_history(self, symbol: str, limit: int = 50) -> dict[str, Any]:
        rows = self.store.fetchall(
            "SELECT * FROM mo_bars WHERE symbol=? ORDER BY ts DESC LIMIT ?",
            (symbol.upper(), limit),
        )
        if not rows:
            # auto refresh offline
            self.historical_refresh(symbol)
            rows = self.store.fetchall(
                "SELECT * FROM mo_bars WHERE symbol=? ORDER BY ts DESC LIMIT ?",
                (symbol.upper(), limit),
            )
        return {"ok": True, "symbol": symbol.upper(), "count": len(rows), "bars": rows, **AUTHORITY_VALUES}

    # ── Exchange status ──────────────────────────────────────────────────
    def list_exchange_status(self) -> dict[str, Any]:
        rows = self.store.fetchall("SELECT * FROM mo_exchange_status ORDER BY exchange")
        return {"ok": True, "count": len(rows), "exchanges": rows, "live_feed": False, **AUTHORITY_VALUES}

    def get_exchange_status(self, exchange: str) -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM mo_exchange_status WHERE exchange=?", (exchange.upper(),))
        if not row:
            st = exchange_status_fixture(exchange)
            return {"ok": True, **st, **AUTHORITY_VALUES}
        return {"ok": True, **row, **AUTHORITY_VALUES}

    # ── Corporate actions ────────────────────────────────────────────────
    def list_corporate_actions(self, symbol: str | None = None) -> dict[str, Any]:
        if symbol:
            # ensure seeded
            existing = self.store.fetchall(
                "SELECT * FROM mo_corporate_actions WHERE symbol=? ORDER BY ex_date",
                (symbol.upper(),),
            )
            if not existing:
                for ca in corporate_actions_fixture(symbol):
                    self.store.execute(
                        "INSERT INTO mo_corporate_actions(id, symbol, action_type, ex_date, amount, ratio, source, detail_json, created_at) "
                        "VALUES(?,?,?,?,?,?,?,?,?)",
                        (_uid("ca"), ca["symbol"], ca["action_type"], ca["ex_date"], ca.get("amount"),
                         ca.get("ratio"), ca["source"], "{}", time.time()),
                    )
                existing = self.store.fetchall(
                    "SELECT * FROM mo_corporate_actions WHERE symbol=? ORDER BY ex_date",
                    (symbol.upper(),),
                )
            return {"ok": True, "count": len(existing), "actions": existing, "read_only": True, **AUTHORITY_VALUES}
        # seed all
        for s in symbol_universe():
            self.list_corporate_actions(s)
        rows = self.store.fetchall("SELECT * FROM mo_corporate_actions ORDER BY symbol, ex_date")
        return {"ok": True, "count": len(rows), "actions": rows, **AUTHORITY_VALUES}

    # ── Benchmarks ───────────────────────────────────────────────────────
    def update_benchmarks(self, *, seed: int = 0) -> dict[str, Any]:
        updated = []
        for b in DEFAULT_BENCHMARKS:
            fx = benchmark_fixture(b, seed=seed)
            if not fx:
                continue
            bid = _uid("bm")
            self.store.execute(
                "INSERT INTO mo_benchmarks(id, benchmark, as_of, level, change_pct, source, created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (bid, fx["benchmark"], fx["as_of"], fx["level"], fx["change_pct"], fx["source"], time.time()),
            )
            updated.append(fx)
        self.store.audit("benchmarks.updated_offline", subject="batch", detail={"n": len(updated)})
        return {
            "ok": True,
            "count": len(updated),
            "benchmarks": updated,
            "source": ObservationSource.OFFLINE_FIXTURE.value,
            "authenticated_live": False,
            **AUTHORITY_VALUES,
        }

    def list_benchmarks(self, limit: int = 20) -> dict[str, Any]:
        rows = self.store.fetchall(
            "SELECT * FROM mo_benchmarks ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        if not rows:
            return self.update_benchmarks()
        return {"ok": True, "count": len(rows), "benchmarks": rows, **AUTHORITY_VALUES}
