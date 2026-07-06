"""Mission — the ROOT object of SaathiOS.

Everything belongs to a Mission: departments, knowledge, workflows, evidence,
learning, revenue. A Mission is the namespace; its `key` is exactly the `project`
that events and evidence already carry, so the whole loop snaps in without a
refactor. Every business — Mr. Yeti IELTS, Surmount Travels, HCG Live Signal, the
hospital cafeteria — is one Mission; a future client is just another instance of
the same operating system, not a special case.

Same architecture for all: identity · objectives · KPIs · knowledge · workflows ·
directors · evidence · learning · revenue. Nothing here is business-specific.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

TYPES = ("business", "client", "product", "startup", "internal", "education", "personal")
STATUSES = ("active", "paused", "archived")

_COLUMNS = ["id", "key", "name", "type", "status", "department", "identity",
            "objectives", "kpis", "directors", "created", "updated"]
_JSON = {"identity", "objectives", "kpis", "directors"}


@dataclass
class Mission:
    key: str                             # namespace == evidence/event `project`
    name: str
    type: str = "business"
    status: str = "active"
    department: str = ""                 # evidence department this Mission's events land in
    identity: dict = field(default_factory=dict)     # company/website/industry/location/…
    objectives: list = field(default_factory=list)
    kpis: dict = field(default_factory=dict)
    directors: list = field(default_factory=list)    # which Directors work inside it
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)

    def to_row(self) -> tuple:
        return (self.id, self.key, self.name, self.type, self.status, self.department,
                json.dumps(self.identity), json.dumps(self.objectives), json.dumps(self.kpis),
                json.dumps(self.directors), self.created, self.updated)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _row_to_dict(row) -> dict:
    d = dict(zip(_COLUMNS, row))
    for c in _JSON:
        try:
            d[c] = json.loads(d[c]) if d[c] else ([] if c in ("objectives", "directors") else {})
        except Exception:
            d[c] = [] if c in ("objectives", "directors") else {}
    return d


class MissionStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else (Path.home() / ".saathi" / "missions.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self):
        return sqlite3.connect(str(self.db_path))

    def _init(self):
        cols = ", ".join(f"{c} {'REAL' if c in ('created', 'updated') else 'TEXT'}" for c in _COLUMNS)
        with self._conn() as c:
            c.execute(f"CREATE TABLE IF NOT EXISTS mission({cols}, PRIMARY KEY(id))")
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_mkey ON mission(key)")

    def create(self, m: Mission) -> str:
        with self._conn() as c:
            c.execute(f"INSERT OR REPLACE INTO mission({','.join(_COLUMNS)}) "
                      f"VALUES({','.join('?'*len(_COLUMNS))})", m.to_row())
        return m.id

    def create_if_absent(self, m: Mission) -> str:
        existing = self.get_by_key(m.key)
        return existing["id"] if existing else self.create(m)

    def get(self, mission_id: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT " + ",".join(_COLUMNS) + " FROM mission WHERE id=?", (mission_id,)).fetchone()
        return _row_to_dict(r) if r else None

    def get_by_key(self, key: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT " + ",".join(_COLUMNS) + " FROM mission WHERE key=?", (key,)).fetchone()
        return _row_to_dict(r) if r else None

    def list(self, *, status: str | None = None) -> list[dict]:
        sql = "SELECT " + ",".join(_COLUMNS) + " FROM mission"
        args = []
        if status:
            sql += " WHERE status=?"; args.append(status)
        sql += " ORDER BY created ASC"
        with self._conn() as c:
            return [_row_to_dict(r) for r in c.execute(sql, args).fetchall()]

    def update(self, mission_id: str, fields: dict) -> bool:
        cur = self.get(mission_id)
        if not cur:
            return False
        allowed = {"name", "type", "status", "department", "identity", "objectives", "kpis", "directors"}
        for k, v in fields.items():
            if k in allowed:
                cur[k] = v
        cur["updated"] = time.time()
        m = Mission(key=cur["key"], name=cur["name"], type=cur["type"], status=cur["status"],
                    department=cur["department"], identity=cur["identity"], objectives=cur["objectives"],
                    kpis=cur["kpis"], directors=cur["directors"])
        m.id = cur["id"]; m.created = cur["created"]; m.updated = cur["updated"]
        self.create(m)
        return True


# the five businesses = five Missions (same OS, different instance)
_SEED = [
    Mission(key="mr_yeti", name="Mr. Yeti IELTS", type="education", department="ai_studio",
            identity={"brand": "Mr. Yeti", "channel": "@pieltsapp", "product": "IELTS video lessons"},
            objectives=["Publish one lesson daily", "Grow YouTube + Telegram", "Feed PIELTS"],
            directors=["research", "creative", "script", "storyboard", "render", "publishing", "learning"]),
    Mission(key="pielts", name="PIELTS Learning", type="education", department="pielts",
            identity={"product": "pielts.web.app", "audience": "IELTS self-study learners"},
            objectives=["Raise learner band scores", "Convert free → premium"],
            directors=["curriculum", "writing_evaluator", "learning"]),
    Mission(key="surmount_travels", name="Grow Surmount Travels", type="client", department="travel",
            identity={"industry": "Travel agency", "location": "Kathmandu"},
            objectives=["Generate qualified leads", "Increase bookings", "Prove ROI per channel"],
            directors=["research", "marketing", "seo", "crm", "proposal", "publishing", "learning"]),
    Mission(key="hcg_signal", name="HCG Live Signal", type="business", department="hcg",
            identity={"product": "Crypto trading signals", "channel": "Telegram"},
            objectives=["Improve win rate", "Grow subscribers", "Report PnL"],
            directors=["signal_engine", "portfolio", "learning"]),
    Mission(key="hcg_canteen", name="Hospital Cafeteria", type="business", department="cafeteria",
            identity={"industry": "Hospital canteen", "location": "Kathmandu"},
            objectives=["Cut food waste", "Raise profit", "Optimise menu"],
            directors=["menu_planner", "learning"]),
]


def seed_missions(store: "MissionStore | None" = None) -> int:
    store = store or default_store()
    n = 0
    for m in _SEED:
        if not store.get_by_key(m.key):
            store.create(m); n += 1
    return n


_default = None
def default_store() -> MissionStore:
    global _default
    if _default is None:
        _default = MissionStore()
    return _default
