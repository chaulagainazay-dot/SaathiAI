"""M204 — Projection rebuild, backup, isolated recovery."""
from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from saathi.platform.tg.paper_activation.durable.events import fingerprint
from saathi.platform.tg.paper_activation.durable.store import DurablePaperStore


def _id(p: str = "prec") -> str:
    return f"{p}_{uuid.uuid4().hex[:12]}"


class RecoveryVerdict:
    VERIFIED = "RECOVERY_VERIFIED"
    VERIFIED_WITH_WARNINGS = "RECOVERY_VERIFIED_WITH_WARNINGS"
    INCOMPLETE = "RECOVERY_INCOMPLETE"
    REJECTED = "RECOVERY_REJECTED"


def create_backup(store: DurablePaperStore, dest_dir: str | Path) -> dict[str, Any]:
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    bid = _id("bak")
    target = dest / f"{bid}.db"
    # checkpoint WAL then copy
    with store._lock:
        store._conn.execute("PRAGMA wal_checkpoint(FULL)")
        store._conn.commit()
        shutil.copy2(store.db_path, target)
    fp = fingerprint({"path": str(target), "size": target.stat().st_size, "mtime": target.stat().st_mtime})
    manifest = {
        "backup_id": bid,
        "path": str(target),
        "source": str(store.db_path),
        "fingerprint": fp,
        "created_at": time.time(),
        "paper_only": True,
    }
    (dest / f"{bid}.manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def verify_backup(manifest_or_path: dict[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(manifest_or_path, (str, Path)):
        p = Path(manifest_or_path)
        if p.suffix == ".json":
            manifest = json.loads(p.read_text())
        else:
            manifest = {"path": str(p), "fingerprint": ""}
    else:
        manifest = manifest_or_path
    path = Path(manifest["path"])
    if not path.is_file():
        return {"ok": False, "verdict": RecoveryVerdict.REJECTED, "reason": "backup_missing"}
    if path.stat().st_size < 100:
        return {"ok": False, "verdict": RecoveryVerdict.REJECTED, "reason": "backup_too_small"}
    # open read-only and count
    try:
        tmp = DurablePaperStore(path)
        h = tmp.health()
        tmp.close()
    except Exception as e:
        return {"ok": False, "verdict": RecoveryVerdict.REJECTED, "reason": str(e)}
    if h.get("status") != "HEALTHY":
        return {"ok": False, "verdict": RecoveryVerdict.INCOMPLETE, "health": h}
    return {
        "ok": True,
        "verdict": RecoveryVerdict.VERIFIED,
        "health": h,
        "backup_id": manifest.get("backup_id"),
        "paper_only": True,
    }


def restore_isolated(
    source_backup: str | Path,
    recovery_db: str | Path,
) -> dict[str, Any]:
    """Copy backup into isolated recovery path; never overwrite source."""
    src = Path(source_backup)
    dst = Path(recovery_db)
    if not src.is_file():
        return {"verdict": RecoveryVerdict.REJECTED, "reason": "source_missing"}
    if dst.resolve() == src.resolve():
        return {"verdict": RecoveryVerdict.REJECTED, "reason": "refuse_overwrite_source"}
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    shutil.copy2(src, dst)
    store = DurablePaperStore(dst)
    health = store.health()
    # reconcile each portfolio
    results = []
    for p in store.list_portfolios():
        positions = store.list_positions(p["id"])
        ledger = store.list_trade_ledger(p["id"])
        cash_ok = float(p["cash"]) >= 0
        results.append({
            "portfolio_id": p["id"],
            "cash_ok": cash_ok,
            "positions": len(positions),
            "ledger_entries": len(ledger),
        })
    events = store.list_events(limit=10000)
    store.close()
    all_ok = all(r["cash_ok"] for r in results) and health.get("status") == "HEALTHY"
    return {
        "verdict": RecoveryVerdict.VERIFIED if all_ok else RecoveryVerdict.VERIFIED_WITH_WARNINGS,
        "recovery_db": str(dst),
        "source_untouched": True,
        "health": health,
        "portfolios": results,
        "event_count": len(events),
        "paper_only": True,
        "live_authorized": False,
    }


def replay_portfolio_cash(store: DurablePaperStore, portfolio_id: str) -> dict[str, Any]:
    """Rebuild cash projection from trade ledger + starting cash (bounded)."""
    p = store.get_portfolio(portfolio_id)
    if not p:
        return {"ok": False, "reason": "portfolio_not_found"}
    start = float(p["starting_cash"])
    cash = start
    for e in store.list_trade_ledger(portfolio_id):
        side = e.get("side", "")
        qty = float(e.get("qty", 0))
        price = float(e.get("price", 0))
        fee = float(e.get("fee", 0))
        if side == "BUY":
            cash -= qty * price + fee
        elif side == "SELL":
            cash += qty * price - fee
    projected = cash
    stored = float(p["cash"])
    delta = abs(projected - stored)
    return {
        "ok": delta < 0.02,
        "starting_cash": start,
        "projected_cash": projected,
        "stored_cash": stored,
        "delta": delta,
        "paper_only": True,
    }
