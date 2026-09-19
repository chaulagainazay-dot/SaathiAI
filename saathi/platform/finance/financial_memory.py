"""Structured Financial Memory — a thin, typed, provenance-first evidence index.

SaathiOS remembers only USEFUL, PERMITTED, structured financial facts and derived
intelligence — never browser sessions, credentials, raw DOM, or viewport frames. It does
not copy whole canonical records; it references them (PortfolioSnapshot / LiveMarketObservation
/ ResearchClaim already exist and stay authoritative) and adds provenance + supersession.

Hard separations (never collapsed):
  FACT · DETERMINISTIC_DERIVATION · MODEL_INTERPRETATION · THESIS · PROPOSAL ·
  OWNER_DECISION · EXECUTION_RESULT
A model interpretation may REFERENCE factual evidence; it can never overwrite it (rows are
immutable; a newer observation is a NEW row that may `supersedes` an older one).

Privacy is enforced at write time: any credential/secret/raw-surface content is REJECTED.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path

from saathi.platform.finance.policy import _PRIVATE_FIELD_RE

# Credential-shaped VALUE patterns (tight — must not reject legitimate financial values like
# amounts, quantities, symbols, or instrument ids). Key-based rejection is the primary guard.
_CRED_VALUE_RE = (
    re.compile(r"(?i)\bBearer\s+\S+"),                                        # bearer token
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}"),  # JWT
    re.compile(r"(?i)\b(password|passcode|secret|api[_-]?key|token|cookie|otp)\b\s*[:=]\s*\S+"),
)
_LONG_OPAQUE_RE = re.compile(r"^[A-Za-z0-9_\-.]{40,}$")   # single long opaque token, no spaces


def _looks_like_credential(v: str) -> bool:
    if any(p.search(v) for p in _CRED_VALUE_RE):
        return True
    s = v.strip()
    # a single long opaque blob that mixes letters AND digits (not a plain number/amount)
    if _LONG_OPAQUE_RE.match(s) and any(ch.isalpha() for ch in s) and any(ch.isdigit() for ch in s):
        return True
    return False


class EvidenceType(str, Enum):
    PORTFOLIO_SNAPSHOT = "PORTFOLIO_SNAPSHOT"
    POSITION_OBSERVATION = "POSITION_OBSERVATION"
    ACCOUNT_SUMMARY = "ACCOUNT_SUMMARY"
    MARKET_OBSERVATION = "MARKET_OBSERVATION"
    RESEARCH_EVIDENCE = "RESEARCH_EVIDENCE"
    CATALYST = "CATALYST"
    TECHNICAL_FEATURE_SET = "TECHNICAL_FEATURE_SET"
    RISK_SNAPSHOT = "RISK_SNAPSHOT"
    INVESTMENT_THESIS = "INVESTMENT_THESIS"
    OWNER_DECISION = "OWNER_DECISION"
    APPROVAL_DECISION = "APPROVAL_DECISION"


class EvidenceClass(str, Enum):
    FACT = "FACT"                                # observed, reproducible
    DETERMINISTIC_DERIVATION = "DETERMINISTIC_DERIVATION"  # computed by a deterministic engine
    MODEL_INTERPRETATION = "MODEL_INTERPRETATION"          # LLM/analytical reading (references facts)
    THESIS = "THESIS"
    PROPOSAL = "PROPOSAL"
    OWNER_DECISION = "OWNER_DECISION"
    EXECUTION_RESULT = "EXECUTION_RESULT"


# Content that must NEVER enter financial memory.
_REJECT_KEYS = frozenset({
    "password", "passcode", "pin", "otp", "totp", "mfa", "2fa", "cookie", "cookies",
    "token", "access_token", "session_token", "api_key", "secret", "private_key", "seed",
    "mnemonic", "dom", "html", "outerhtml", "innerhtml", "raw_html", "frame", "frame_b64",
    "screenshot", "keystroke", "keystrokes", "storage_state", "captcha",
})


class FinancialMemoryRejected(ValueError):
    """Raised when a record would persist credentials / raw surface / secrets."""


def _scan_reject(payload: dict) -> None:
    """Reject if any key is reserved-sensitive or any string value looks like a secret."""
    for k, v in (payload or {}).items():
        kl = str(k).strip().lower()
        if kl in _REJECT_KEYS or _PRIVATE_FIELD_RE.search(kl):
            raise FinancialMemoryRejected(f"rejected sensitive key: {k}")
        if isinstance(v, str):
            if _looks_like_credential(v):
                raise FinancialMemoryRejected(f"rejected credential-looking value for key: {k}")
        elif isinstance(v, dict):
            _scan_reject(v)


def _content_hash(d: dict) -> str:
    return hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()


@dataclass(frozen=True)
class FinancialEvidence:
    provider: str
    evidence_type: str                 # EvidenceType value
    evidence_class: str                # EvidenceClass value
    observed_at: float
    source_type: str = ""              # e.g. OWNER_AUTHENTICATED_BROWSER_OBSERVED / OFFICIAL_PAGE_OBSERVED
    source_url: str = ""
    account_scope: str = ""            # opaque scope label, never an account number
    instrument_id: str = ""
    freshness: str = ""
    quality: str = ""
    provenance: str = ""               # short human-readable provenance
    runtime_id: str = ""
    session_id: str = ""
    supersedes: str = ""               # prior evidence_id this replaces (never mutates it)
    canonical_ref: str = ""            # id of the authoritative record (snapshot_id, obs id, …)
    payload: dict = field(default_factory=dict)   # bounded, sanitized — no secrets/raw surface
    available_at: float | None = None
    evidence_id: str = field(default_factory=lambda: "fev_" + uuid.uuid4().hex[:16])
    content_hash: str = ""
    created_at: float = field(default_factory=time.time)

    def with_hash(self) -> "FinancialEvidence":
        from dataclasses import replace
        h = _content_hash({"t": self.evidence_type, "c": self.evidence_class,
                           "i": self.instrument_id, "p": self.payload, "o": self.observed_at,
                           "ref": self.canonical_ref})
        return replace(self, content_hash=h)

    def to_public(self) -> dict:
        return asdict(self)


_COLS = ("evidence_id", "provider", "evidence_type", "evidence_class", "source_type",
         "source_url", "account_scope", "instrument_id", "observed_at", "available_at",
         "freshness", "quality", "provenance", "content_hash", "runtime_id", "session_id",
         "supersedes", "canonical_ref", "payload", "created_at")


class FinancialMemoryStore:
    """Immutable, append-only typed evidence store (SQLite). Latest-state via query."""

    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path) if db_path else (Path.home() / ".saathi" / "finance_memory.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self):
        c = sqlite3.connect(str(self.db_path))
        c.row_factory = sqlite3.Row
        return c

    def _init(self):
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS financial_evidence (
                evidence_id TEXT PRIMARY KEY, provider TEXT, evidence_type TEXT,
                evidence_class TEXT, source_type TEXT, source_url TEXT, account_scope TEXT,
                instrument_id TEXT, observed_at REAL, available_at REAL, freshness TEXT,
                quality TEXT, provenance TEXT, content_hash TEXT, runtime_id TEXT,
                session_id TEXT, supersedes TEXT, canonical_ref TEXT, payload TEXT,
                created_at REAL)""")
            c.execute("CREATE INDEX IF NOT EXISTS ix_fe_type ON financial_evidence(provider, evidence_type, observed_at)")
            c.execute("CREATE INDEX IF NOT EXISTS ix_fe_inst ON financial_evidence(instrument_id, observed_at)")

    def record(self, ev: FinancialEvidence) -> str:
        _scan_reject(ev.payload)                  # privacy gate: never persist secrets/raw surface
        ev = ev.with_hash()
        row = ev.to_public()
        row["payload"] = json.dumps(ev.payload, default=str)
        with self._conn() as c:
            c.execute(f"INSERT OR REPLACE INTO financial_evidence ({','.join(_COLS)}) "
                      f"VALUES ({','.join('?' for _ in _COLS)})", [row[k] for k in _COLS])
        return ev.evidence_id

    def _rows(self, sql: str, args: list) -> list[dict]:
        with self._conn() as c:
            out = []
            for r in c.execute(sql, args).fetchall():
                d = dict(r)
                try:
                    d["payload"] = json.loads(d.get("payload") or "{}")
                except Exception:
                    d["payload"] = {}
                out.append(d)
            return out

    def latest(self, *, provider: str | None = None, evidence_type: str | None = None,
               instrument_id: str | None = None, limit: int = 20) -> list[dict]:
        where, args = [], []
        if provider:
            where.append("provider=?"); args.append(provider)
        if evidence_type:
            where.append("evidence_type=?"); args.append(evidence_type)
        if instrument_id:
            where.append("instrument_id=?"); args.append(instrument_id)
        sql = "SELECT * FROM financial_evidence"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY observed_at DESC LIMIT ?"; args.append(limit)
        return self._rows(sql, args)

    def history(self, instrument_id: str, *, limit: int = 50) -> list[dict]:
        return self._rows("SELECT * FROM financial_evidence WHERE instrument_id=? "
                          "ORDER BY observed_at DESC LIMIT ?", [instrument_id, limit])

    def get(self, evidence_id: str) -> dict | None:
        r = self._rows("SELECT * FROM financial_evidence WHERE evidence_id=?", [evidence_id])
        return r[0] if r else None

    def count(self, *, provider: str | None = None) -> int:
        with self._conn() as c:
            if provider:
                return c.execute("SELECT COUNT(*) FROM financial_evidence WHERE provider=?",
                                 [provider]).fetchone()[0]
            return c.execute("SELECT COUNT(*) FROM financial_evidence").fetchone()[0]

    def clear_session(self, session_id: str) -> int:
        """Remove session-derived temporary evidence (owner control). Facts keyed to a
        runtime session only; canonical snapshots persist independently by design."""
        with self._conn() as c:
            cur = c.execute("DELETE FROM financial_evidence WHERE session_id=? AND session_id!=''",
                            [session_id])
            return cur.rowcount


# ── composition: build typed evidence from existing canonical records ────────────
def portfolio_evidence(snapshot_view: dict, *, provider: str, runtime_id: str = "",
                       session_id: str = "", supersedes: str = "",
                       now: float | None = None) -> FinancialEvidence:
    """From a browser_portfolio.portfolio_view(snapshot) dict → PORTFOLIO_SNAPSHOT FACT.
    Stores the public projection (no cost basis inference, no raw page)."""
    now = now if now is not None else time.time()
    v = snapshot_view or {}
    payload = {
        "currency": v.get("currency"), "asset_count": v.get("asset_count"),
        "total_value": v.get("total_value"), "top_concentration_pct": v.get("top_concentration_pct"),
        "largest_position": (v.get("largest_position") or {}).get("symbol"),
        "symbols": [p.get("symbol") for p in v.get("positions", [])],
    }
    return FinancialEvidence(
        provider=provider.upper(), evidence_type=EvidenceType.PORTFOLIO_SNAPSHOT.value,
        evidence_class=EvidenceClass.FACT.value, observed_at=now,
        source_type=v.get("source") or "OWNER_AUTHENTICATED_BROWSER_OBSERVED",
        freshness="FRESH", quality="OWNER_OBSERVED", provenance="owner-authenticated browser read",
        runtime_id=runtime_id, session_id=session_id, supersedes=supersedes,
        canonical_ref=v.get("snapshot_id", ""), payload=payload)


def position_evidences(snapshot_view: dict, *, provider: str, runtime_id: str = "",
                       session_id: str = "", now: float | None = None) -> list[FinancialEvidence]:
    now = now if now is not None else time.time()
    out = []
    for p in (snapshot_view or {}).get("positions", []):
        out.append(FinancialEvidence(
            provider=provider.upper(), evidence_type=EvidenceType.POSITION_OBSERVATION.value,
            evidence_class=EvidenceClass.FACT.value, observed_at=now,
            source_type=snapshot_view.get("source") or "OWNER_AUTHENTICATED_BROWSER_OBSERVED",
            instrument_id=p.get("instrument_id") or p.get("symbol", ""),
            freshness="FRESH", quality="OWNER_OBSERVED", provenance="owner portfolio position",
            runtime_id=runtime_id, session_id=session_id,
            payload={"symbol": p.get("symbol"), "quantity": p.get("quantity"),
                     "market_value": p.get("market_value"), "currency": snapshot_view.get("currency"),
                     "current_price": p.get("current_price"),
                     "current_price_source": p.get("current_price_source")}))
    return out


def market_evidence(*, provider: str, instrument_id: str, ltp, source_type: str,
                    freshness: str = "", now: float | None = None) -> FinancialEvidence:
    """Official/public market observation → MARKET_OBSERVATION FACT (current price authority)."""
    now = now if now is not None else time.time()
    return FinancialEvidence(
        provider=provider.upper(), evidence_type=EvidenceType.MARKET_OBSERVATION.value,
        evidence_class=EvidenceClass.FACT.value, observed_at=now, source_type=source_type,
        instrument_id=instrument_id, freshness=freshness or "FRESH", quality="MARKET_OBSERVED",
        provenance="market observation", payload={"ltp": None if ltp is None else str(ltp)})


_STORE: FinancialMemoryStore | None = None


def get_memory_store() -> FinancialMemoryStore:
    global _STORE
    if _STORE is None:
        _STORE = FinancialMemoryStore()
    return _STORE
