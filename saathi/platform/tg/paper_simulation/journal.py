"""Trade journal for paper simulation."""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.paper_simulation.models import AUTHORITY_VALUES
from saathi.platform.tg.paper_simulation.storage import PaperSimStore, _uid


class TradeJournal:
    def __init__(self, store: PaperSimStore):
        self.store = store

    def write(self, title: str, body: str, *, kind: str = "note", refs: dict | None = None) -> dict[str, Any]:
        jid = _uid("jnl")
        self.store.execute(
            "INSERT INTO ps_journal(id, kind, title, body, refs_json, created_at) VALUES(?,?,?,?,?,?)",
            (jid, kind, title, body, json.dumps(refs or {}, sort_keys=True, default=str), time.time()),
        )
        return {"ok": True, "entry_id": jid, "title": title, **AUTHORITY_VALUES}

    def list(self, limit: int = 50) -> dict[str, Any]:
        rows = self.store.fetchall(
            "SELECT * FROM ps_journal ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        for r in rows:
            r["refs"] = json.loads(r.pop("refs_json") or "{}")
        return {"ok": True, "count": len(rows), "entries": rows, **AUTHORITY_VALUES}
