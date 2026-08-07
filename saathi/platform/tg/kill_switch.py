"""Persistent, audited kill switches. Cannot be overridden by strategy or LLM."""
from __future__ import annotations

import copy
import time
from typing import Any

from saathi.platform.tg.domain import KillSwitchScope, TradingGuardianKillSwitch


class KillSwitchStore:
    def __init__(self) -> None:
        self._items: dict[str, TradingGuardianKillSwitch] = {}
        self._audit: list[dict[str, Any]] = []

    def activate(
        self,
        *,
        scope: KillSwitchScope | str,
        scope_ref: str = "",
        reason: str,
        activated_by: str,
        org_id: str = "",
        workspace_id: str = "",
        correlation_id: str = "",
        source_identity: str = "operator",
    ) -> TradingGuardianKillSwitch:
        sc = KillSwitchScope(scope) if not isinstance(scope, KillSwitchScope) else scope
        if not reason:
            raise ValueError("kill switch reason required")
        if source_identity in ("strategy", "llm", "agent") or activated_by.startswith(("strategy:", "llm:", "agent:")):
            raise PermissionError("strategy/LLM/agent cannot activate or override kill switch authority model")
        key = self._key(sc, scope_ref, org_id, workspace_id)
        existing = self._items.get(key)
        if existing and existing.active:
            existing.reason = reason
            existing.updated_at = time.time()
            existing.activated_by = activated_by
            ks = existing
        else:
            ks = TradingGuardianKillSwitch(
                scope=sc,
                scope_ref=scope_ref,
                active=True,
                reason=reason,
                activated_by=activated_by,
                source_identity=source_identity,
                correlation_id=correlation_id,
                org_id=org_id,
                workspace_id=workspace_id,
            )
            self._items[key] = ks
        self._audit.append({
            "action": "ACTIVATE",
            "ts": time.time(),
            "scope": sc.value,
            "scope_ref": scope_ref,
            "reason": reason,
            "activated_by": activated_by,
            "org_id": org_id,
            "workspace_id": workspace_id,
        })
        return copy.deepcopy(ks)

    def deactivate(
        self,
        *,
        scope: KillSwitchScope | str,
        scope_ref: str = "",
        deactivated_by: str,
        org_id: str = "",
        workspace_id: str = "",
        reason: str = "operator_clear",
    ) -> TradingGuardianKillSwitch | None:
        if deactivated_by.startswith(("strategy:", "llm:", "agent:")):
            raise PermissionError("strategy/LLM/agent cannot clear kill switch")
        sc = KillSwitchScope(scope) if not isinstance(scope, KillSwitchScope) else scope
        key = self._key(sc, scope_ref, org_id, workspace_id)
        ks = self._items.get(key)
        if not ks:
            return None
        ks.active = False
        ks.updated_at = time.time()
        ks.reason = reason
        self._audit.append({
            "action": "DEACTIVATE",
            "ts": time.time(),
            "scope": sc.value,
            "scope_ref": scope_ref,
            "reason": reason,
            "deactivated_by": deactivated_by,
        })
        return copy.deepcopy(ks)

    def is_blocked(
        self,
        *,
        org_id: str = "",
        workspace_id: str = "",
        strategy_id: str = "",
        instrument: str = "",
        portfolio_id: str = "",
        market: str = "",
        automation_id: str = "",
    ) -> dict[str, Any]:
        """Return blocked status. Active switches match by scope + ref; empty org/workspace
        on a switch acts as a wildcard within that scope (immediate, fail-closed)."""
        ref_for = {
            KillSwitchScope.GLOBAL: "",
            KillSwitchScope.TRADING_GUARDIAN: "",
            KillSwitchScope.WORKSPACE: workspace_id,
            KillSwitchScope.STRATEGY: strategy_id,
            KillSwitchScope.INSTRUMENT: instrument,
            KillSwitchScope.PORTFOLIO: portfolio_id,
            KillSwitchScope.MARKET: market,
            KillSwitchScope.AUTOMATION: automation_id,
        }
        for ks in self._items.values():
            if not ks.active:
                continue
            # org/workspace isolation: empty on switch = global for that scope
            if ks.org_id and org_id and ks.org_id != org_id:
                continue
            if ks.workspace_id and workspace_id and ks.workspace_id != workspace_id:
                continue
            expected_ref = ref_for.get(ks.scope, "")
            if ks.scope in (KillSwitchScope.GLOBAL, KillSwitchScope.TRADING_GUARDIAN):
                return {
                    "blocked": True,
                    "scope": ks.scope.value,
                    "scope_ref": ks.scope_ref,
                    "reason": ks.reason,
                    "kill_switch_id": ks.id,
                }
            if not expected_ref:
                continue
            if ks.scope_ref == expected_ref or ks.scope_ref == "*":
                return {
                    "blocked": True,
                    "scope": ks.scope.value,
                    "scope_ref": ks.scope_ref,
                    "reason": ks.reason,
                    "kill_switch_id": ks.id,
                }
        return {"blocked": False, "reason": "clear"}

    def status(self, *, org_id: str = "", workspace_id: str = "") -> list[dict[str, Any]]:
        out = []
        for ks in self._items.values():
            if org_id and ks.org_id and ks.org_id != org_id:
                continue
            if workspace_id and ks.workspace_id and ks.workspace_id != workspace_id:
                continue
            out.append(ks.to_public())
        return out

    def audit_log(self) -> list[dict[str, Any]]:
        return list(self._audit)

    def _key(self, scope: KillSwitchScope, scope_ref: str, org_id: str, workspace_id: str) -> str:
        return f"{org_id}|{workspace_id}|{scope.value}|{scope_ref}"
