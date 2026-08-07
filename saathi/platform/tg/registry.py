"""M166 — Versioned Strategy Registry.

Strategies are registered with immutable versions after activation.
Changes require a new version. Tenant-scoped. Deterministic fingerprints.
"""
from __future__ import annotations

import copy
import time
from typing import Any

from saathi.platform.tg.domain import (
    StrategyActivation,
    StrategyParameterSet,
    StrategyVersion,
    TradingStrategy,
    strategy_fingerprint,
)


class RegistryError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class StrategyRegistry:
    """In-memory + optional store-backed strategy registry."""

    def __init__(self) -> None:
        self._by_id: dict[str, TradingStrategy] = {}
        self._by_slug: dict[tuple[str, str, str], str] = {}  # (org, ws, slug) -> id

    def register(
        self,
        *,
        name: str,
        slug: str,
        description: str = "",
        family: str = "",
        source_identity: str = "operator",
        org_id: str = "",
        workspace_id: str = "",
        project_id: str = "",
        mission_id: str = "",
        version: str = "1.0.0",
        parameters: dict[str, Any] | None = None,
        parameter_schema: dict[str, Any] | None = None,
        supported_instruments: list[str] | None = None,
        supported_timeframes: list[str] | None = None,
        required_data_fields: list[str] | None = None,
        regime_compatibility: list[str] | None = None,
        assumptions: list[str] | None = None,
        invalidation_conditions: list[str] | None = None,
        stop_logic: str = "",
        holding_horizon: str = "",
        confidence_components: list[str] | None = None,
        reproducibility: dict[str, Any] | None = None,
        activate: bool = False,
        policy_version: str = "1.0.0",
        correlation_id: str = "",
    ) -> TradingStrategy:
        if not name or not slug:
            raise RegistryError("INVALID_STRATEGY", "name and slug required")
        key = (org_id, workspace_id, slug)
        if key in self._by_slug:
            raise RegistryError("DUPLICATE_SLUG", f"strategy slug already registered: {slug}")

        params = StrategyParameterSet(
            parameters=dict(parameters or {}),
            parameter_schema=dict(parameter_schema or {}),
        )
        fp_payload = {
            "slug": slug,
            "version": version,
            "family": family,
            "parameters": params.parameters,
            "parameter_schema": params.parameter_schema,
            "supported_instruments": list(supported_instruments or []),
            "supported_timeframes": list(supported_timeframes or []),
            "required_data_fields": list(required_data_fields or []),
            "regime_compatibility": list(regime_compatibility or []),
            "stop_logic": stop_logic,
            "holding_horizon": holding_horizon,
        }
        fp = strategy_fingerprint(fp_payload)
        sv = StrategyVersion(
            strategy_id="",  # filled after parent id known
            version=version,
            source_identity=source_identity,
            parameters=params,
            supported_instruments=list(supported_instruments or []),
            supported_timeframes=list(supported_timeframes or []),
            required_data_fields=list(required_data_fields or []),
            regime_compatibility=list(regime_compatibility or []),
            activation=StrategyActivation.REGISTERED,
            fingerprint=fp,
            reproducibility=dict(reproducibility or {"engine": "m166.tg", "deterministic": True}),
            assumptions=list(assumptions or []),
            invalidation_conditions=list(invalidation_conditions or []),
            stop_logic=stop_logic,
            holding_horizon=holding_horizon,
            confidence_components=list(confidence_components or []),
            policy_version=policy_version,
            correlation_id=correlation_id,
            org_id=org_id,
            workspace_id=workspace_id,
            project_id=project_id,
            mission_id=mission_id,
        )
        strat = TradingStrategy(
            name=name,
            slug=slug,
            description=description,
            family=family,
            source_identity=source_identity,
            activation=StrategyActivation.REGISTERED,
            latest_version=version,
            versions=[sv],
            org_id=org_id,
            workspace_id=workspace_id,
            project_id=project_id,
            mission_id=mission_id,
            paper_only=True,
            live_authorized=False,
        )
        sv.strategy_id = strat.id
        self._by_id[strat.id] = strat
        self._by_slug[key] = strat.id
        if activate:
            self.activate_version(strat.id, version)
        return copy.deepcopy(self._by_id[strat.id])

    def activate_version(self, strategy_id: str, version: str) -> TradingStrategy:
        strat = self._require(strategy_id)
        target = self._find_version(strat, version)
        if target.deprecated:
            raise RegistryError("DEPRECATED", "cannot activate deprecated version")
        # freeze: immutable after activation
        target.freeze()
        strat.activation = StrategyActivation.ACTIVE
        strat.latest_version = version
        strat.updated_at = time.time()
        # mark other active versions as registered (not multi-active)
        for v in strat.versions:
            if v.version != version and v.activation == StrategyActivation.ACTIVE:
                v.activation = StrategyActivation.REGISTERED
        return copy.deepcopy(strat)

    def create_version(
        self,
        strategy_id: str,
        *,
        version: str,
        parameters: dict[str, Any] | None = None,
        parameter_schema: dict[str, Any] | None = None,
        source_identity: str = "operator",
        supported_instruments: list[str] | None = None,
        supported_timeframes: list[str] | None = None,
        required_data_fields: list[str] | None = None,
        regime_compatibility: list[str] | None = None,
        assumptions: list[str] | None = None,
        invalidation_conditions: list[str] | None = None,
        stop_logic: str = "",
        holding_horizon: str = "",
        confidence_components: list[str] | None = None,
        reproducibility: dict[str, Any] | None = None,
        policy_version: str = "1.0.0",
        correlation_id: str = "",
    ) -> StrategyVersion:
        strat = self._require(strategy_id)
        if any(v.version == version for v in strat.versions):
            raise RegistryError("VERSION_EXISTS", f"version {version} already exists")
        # Base on latest version metadata when not fully specified
        base = strat.versions[-1] if strat.versions else None
        params = StrategyParameterSet(
            parameters=dict(parameters if parameters is not None else (base.parameters.parameters if base else {})),
            parameter_schema=dict(
                parameter_schema if parameter_schema is not None
                else (base.parameters.parameter_schema if base else {})
            ),
        )
        si = supported_instruments if supported_instruments is not None else (list(base.supported_instruments) if base else [])
        st = supported_timeframes if supported_timeframes is not None else (list(base.supported_timeframes) if base else [])
        rdf = required_data_fields if required_data_fields is not None else (list(base.required_data_fields) if base else [])
        rc = regime_compatibility if regime_compatibility is not None else (list(base.regime_compatibility) if base else [])
        fp_payload = {
            "slug": strat.slug,
            "version": version,
            "family": strat.family,
            "parameters": params.parameters,
            "parameter_schema": params.parameter_schema,
            "supported_instruments": si,
            "supported_timeframes": st,
            "required_data_fields": rdf,
            "regime_compatibility": rc,
            "stop_logic": stop_logic or (base.stop_logic if base else ""),
            "holding_horizon": holding_horizon or (base.holding_horizon if base else ""),
        }
        sv = StrategyVersion(
            strategy_id=strat.id,
            version=version,
            source_identity=source_identity,
            parameters=params,
            supported_instruments=si,
            supported_timeframes=st,
            required_data_fields=rdf,
            regime_compatibility=rc,
            activation=StrategyActivation.REGISTERED,
            fingerprint=strategy_fingerprint(fp_payload),
            reproducibility=dict(reproducibility or {"engine": "m166.tg", "deterministic": True}),
            assumptions=list(assumptions if assumptions is not None else (base.assumptions if base else [])),
            invalidation_conditions=list(
                invalidation_conditions if invalidation_conditions is not None
                else (base.invalidation_conditions if base else [])
            ),
            stop_logic=stop_logic or (base.stop_logic if base else ""),
            holding_horizon=holding_horizon or (base.holding_horizon if base else ""),
            confidence_components=list(
                confidence_components if confidence_components is not None
                else (base.confidence_components if base else [])
            ),
            policy_version=policy_version,
            correlation_id=correlation_id,
            org_id=strat.org_id,
            workspace_id=strat.workspace_id,
            project_id=strat.project_id,
            mission_id=strat.mission_id,
        )
        strat.versions.append(sv)
        strat.latest_version = version
        strat.updated_at = time.time()
        return copy.deepcopy(sv)

    def mutate_activated_version(self, strategy_id: str, version: str, **_kwargs: Any) -> None:
        """Explicit rejection path: activated versions are immutable."""
        strat = self._require(strategy_id)
        target = self._find_version(strat, version)
        if target.immutable or target.activation == StrategyActivation.ACTIVE:
            raise RegistryError(
                "IMMUTABLE_VERSION",
                f"strategy version {version} is immutable after activation; create a new version",
            )
        raise RegistryError("NOT_ACTIVATED", "version not activated; use create_version to change draft parameters")

    def deprecate(self, strategy_id: str, *, version: str | None = None) -> TradingStrategy:
        strat = self._require(strategy_id)
        if version is None:
            strat.deprecated = True
            strat.activation = StrategyActivation.DEPRECATED
            for v in strat.versions:
                v.deprecated = True
                v.activation = StrategyActivation.DEPRECATED
        else:
            target = self._find_version(strat, version)
            target.deprecated = True
            target.activation = StrategyActivation.DEPRECATED
        strat.updated_at = time.time()
        return copy.deepcopy(strat)

    def suspend(self, strategy_id: str) -> TradingStrategy:
        strat = self._require(strategy_id)
        strat.activation = StrategyActivation.SUSPENDED
        strat.updated_at = time.time()
        return copy.deepcopy(strat)

    def get(self, strategy_id: str, *, org_id: str = "", workspace_id: str = "") -> TradingStrategy:
        strat = self._require(strategy_id)
        if org_id and strat.org_id and strat.org_id != org_id:
            raise RegistryError("TENANT_ISOLATION", "strategy not visible in this org")
        if workspace_id and strat.workspace_id and strat.workspace_id != workspace_id:
            raise RegistryError("TENANT_ISOLATION", "strategy not visible in this workspace")
        return copy.deepcopy(strat)

    def get_by_slug(self, slug: str, *, org_id: str = "", workspace_id: str = "") -> TradingStrategy | None:
        sid = self._by_slug.get((org_id, workspace_id, slug))
        if not sid:
            return None
        return self.get(sid, org_id=org_id, workspace_id=workspace_id)

    def list(
        self,
        *,
        org_id: str = "",
        workspace_id: str = "",
        include_deprecated: bool = False,
    ) -> list[TradingStrategy]:
        out: list[TradingStrategy] = []
        for s in self._by_id.values():
            if org_id and s.org_id and s.org_id != org_id:
                continue
            if workspace_id and s.workspace_id and s.workspace_id != workspace_id:
                continue
            if s.deprecated and not include_deprecated:
                continue
            out.append(copy.deepcopy(s))
        return sorted(out, key=lambda x: x.created_at)

    def get_version(self, strategy_id: str, version: str) -> StrategyVersion:
        strat = self._require(strategy_id)
        return copy.deepcopy(self._find_version(strat, version))

    def fingerprint(self, strategy_id: str, version: str) -> str:
        return self.get_version(strategy_id, version).fingerprint

    def _require(self, strategy_id: str) -> TradingStrategy:
        if strategy_id not in self._by_id:
            raise RegistryError("NOT_FOUND", f"strategy {strategy_id} not found")
        return self._by_id[strategy_id]

    def _find_version(self, strat: TradingStrategy, version: str) -> StrategyVersion:
        for v in strat.versions:
            if v.version == version:
                return v
        raise RegistryError("VERSION_NOT_FOUND", f"version {version} not found for {strat.id}")
