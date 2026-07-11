"""M13.5 database integrity — real PRAGMA integrity_check per app db.

Never auto-migrates destructive changes; this is read-only inspection.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "data"

APP_DBS = ["chat.db", "memory.db", "agent_runtime.db", "voice_os.db", "ceo_os.db",
           "studio_os.db", "connectors.db"]


def check_db(path: Path) -> dict:
    if not path.exists():
        return {"db": path.name, "present": False, "ok": True, "note": "not created yet"}
    try:
        c = sqlite3.connect(str(path))
        integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
        fk = c.execute("PRAGMA foreign_key_check").fetchall()
        tables = [r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        c.close()
        ok = integrity == "ok" and not fk
        return {"db": path.name, "present": True, "ok": ok,
                "integrity": integrity, "fk_violations": len(fk),
                "tables": len(tables), "size_bytes": path.stat().st_size}
    except sqlite3.DatabaseError as exc:
        return {"db": path.name, "present": True, "ok": False,
                "error": f"corruption: {exc}"}


def check_all(data_dir: Path | None = None) -> dict:
    d = data_dir or DATA
    results = [check_db(d / name) for name in APP_DBS]
    return {"all_ok": all(r["ok"] for r in results), "databases": results}
