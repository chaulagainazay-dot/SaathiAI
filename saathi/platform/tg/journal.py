"""M173 — Append-only Trading Journal. Entries are immutable after write."""
from __future__ import annotations

import copy
import json
from decimal import Decimal
from typing import Any

from saathi.platform.tg.domain import TradeJournalEntry


class JournalError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class TradeJournal:
    def __init__(self) -> None:
        self._entries: list[TradeJournalEntry] = []
        self._by_id: dict[str, TradeJournalEntry] = {}

    def append(self, entry: TradeJournalEntry) -> TradeJournalEntry:
        if entry.id in self._by_id:
            raise JournalError("DUPLICATE", "journal entry ids must be unique")
        entry.immutable = True
        stored = copy.deepcopy(entry)
        self._entries.append(stored)
        self._by_id[stored.id] = stored
        return copy.deepcopy(stored)

    def get(self, entry_id: str) -> TradeJournalEntry:
        if entry_id not in self._by_id:
            raise JournalError("NOT_FOUND", f"journal entry {entry_id} not found")
        return copy.deepcopy(self._by_id[entry_id])

    def mutate(self, entry_id: str, **_kwargs: Any) -> None:
        raise JournalError("IMMUTABLE", "trade journal entries cannot be mutated")

    def list(
        self,
        *,
        org_id: str = "",
        workspace_id: str = "",
        strategy_id: str = "",
        limit: int = 100,
    ) -> list[TradeJournalEntry]:
        out = []
        for e in reversed(self._entries):
            if org_id and e.org_id and e.org_id != org_id:
                continue
            if workspace_id and e.workspace_id and e.workspace_id != workspace_id:
                continue
            if strategy_id and e.strategy_id != strategy_id:
                continue
            out.append(copy.deepcopy(e))
            if len(out) >= limit:
                break
        return out

    def export(
        self,
        *,
        org_id: str = "",
        workspace_id: str = "",
        strategy_id: str = "",
    ) -> str:
        rows = [e.to_public() for e in self.list(
            org_id=org_id, workspace_id=workspace_id, strategy_id=strategy_id, limit=10_000
        )]
        return json.dumps({
            "schema_version": "m173.journal.export.v1",
            "paper_only": True,
            "funds_label": "SIMULATED",
            "count": len(rows),
            "entries": rows,
        }, indent=2, default=str)

    def record_lifecycle(
        self,
        *,
        proposal: dict[str, Any],
        signal: dict[str, Any] | None = None,
        policy_gates: list[dict[str, Any]] | None = None,
        risk: dict[str, Any] | None = None,
        approval: dict[str, Any] | None = None,
        order: dict[str, Any] | None = None,
        fills: list[dict[str, Any]] | None = None,
        regime: list[str] | None = None,
        market_context: dict[str, Any] | None = None,
        exit_reason: str = "",
        pnl: Decimal = Decimal("0"),
        fees: Decimal = Decimal("0"),
        slippage: Decimal = Decimal("0"),
        rule_violations: list[str] | None = None,
        operator_notes: str = "",
        evidence_refs: list[str] | None = None,
        org_id: str = "",
        workspace_id: str = "",
        correlation_id: str = "",
        policy_version: str = "1.0.0",
    ) -> TradeJournalEntry:
        entry = TradeJournalEntry(
            proposal_id=str(proposal.get("id", "")),
            strategy_id=str(proposal.get("strategy_id", "")),
            strategy_version=str(proposal.get("strategy_version", "")),
            regime=list(regime or proposal.get("regime_labels") or []),
            signal=dict(signal or {}),
            proposal=dict(proposal),
            policy_gates=list(policy_gates or []),
            risk_calculation=dict(risk or {}),
            approval=dict(approval or {}),
            order=dict(order or {}),
            fills=list(fills or []),
            stop_target={
                "stop_price": proposal.get("stop_price"),
                "take_profit_price": proposal.get("take_profit_price"),
            },
            exit_reason=exit_reason,
            pnl=pnl,
            fees=fees,
            slippage=slippage,
            rule_violations=list(rule_violations or []),
            operator_notes=operator_notes,
            evidence_refs=list(evidence_refs or []),
            market_context=dict(market_context or {}),
            correlation_id=correlation_id or str(proposal.get("correlation_id", "")),
            policy_version=policy_version,
            org_id=org_id or str(proposal.get("org_id", "")),
            workspace_id=workspace_id or str(proposal.get("workspace_id", "")),
        )
        return self.append(entry)
