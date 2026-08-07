"""M216–M223 Broker Sandbox Architecture Service facade.

Composes abstraction, registry, credentials, emulator, trust, failure, security,
and control center. PAPER ONLY. Physically incapable of real broker connections.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from saathi.platform.tg.broker_sandbox.abstraction import abstraction_surface
from saathi.platform.tg.broker_sandbox.control_center import SandboxControlCenter
from saathi.platform.tg.broker_sandbox.credentials import (
    CredentialTrustError,
    CredentialTrustFramework,
)
from saathi.platform.tg.broker_sandbox.emulator import SandboxBrokerError, SandboxEmulator
from saathi.platform.tg.broker_sandbox.failure import FAILURE_SCENARIOS, FailureRecoverySimulator
from saathi.platform.tg.broker_sandbox.models import (
    ENGINE_VERSION,
    LLM_BOUNDARY,
    PAPER_POSTURE,
    SCHEMA_VERSION,
    TERMINAL_VERDICT,
    LIVE_TRADING_AUTHORIZED,
    LIVE_ORDER_CAPABLE,
    BROKER_CREDENTIAL_SUPPORT,
    REAL_BROKER_CONNECTION_CAPABLE,
)
from saathi.platform.tg.broker_sandbox.registry import CapabilityRegistry
from saathi.platform.tg.broker_sandbox.security import SecurityValidator
from saathi.platform.tg.broker_sandbox.store import SandboxStore
from saathi.platform.tg.broker_sandbox.trust_pipeline import (
    TrustApprovalPipeline,
    TrustPipelineError,
)


class BrokerSandboxError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class BrokerSandboxService:
    def __init__(self, db_path: str | Path | None = None):
        self.store = SandboxStore(db_path)
        self.registry = CapabilityRegistry(self.store)
        self.credentials = CredentialTrustFramework(self.store)
        self.emulator = SandboxEmulator(self.store)
        self.trust = TrustApprovalPipeline(self.store)
        self.failure = FailureRecoverySimulator(self.store, self.emulator, self.credentials)
        self.security = SecurityValidator(
            self.store, self.registry, self.credentials, self.trust, self.emulator,
        )
        self.control = SandboxControlCenter(
            self.store, self.registry, self.credentials, self.trust,
            self.emulator, self.failure, self.security,
        )

    def posture(self) -> dict[str, Any]:
        return {
            **PAPER_POSTURE,
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "milestones": "M216-M223",
            "terminal_verdict_target": TERMINAL_VERDICT,
            "llm_boundary": dict(LLM_BOUNDARY),
            "live_trading_authorized": LIVE_TRADING_AUTHORIZED,
            "live_order_capable": LIVE_ORDER_CAPABLE,
            "broker_credential_support": BROKER_CREDENTIAL_SUPPORT,
            "real_broker_connection_capable": REAL_BROKER_CONNECTION_CAPABLE,
            "disclaimer": PAPER_POSTURE["disclaimer"],
        }

    def terminal_verdict(self) -> dict[str, Any]:
        return {
            "verdict": TERMINAL_VERDICT,
            "paper_only": True,
            "live_trading_authorized": False,
            "broker_connections_exist": False,
            "api_credentials_created": False,
            "live_trading_is_authorized": False,
            "sandbox_can_execute_real_orders": False,
            "statements": [
                "THE SYSTEM REMAINS PAPER ONLY.",
                "NO BROKER CONNECTIONS EXIST.",
                "NO API CREDENTIALS WERE CREATED.",
                "NO LIVE TRADING IS AUTHORIZED.",
                "THE SANDBOX CANNOT EXECUTE REAL ORDERS.",
            ],
            "limitations": [
                "Single-host SQLite",
                "Catalog brokers are design metadata only",
                "Credential references never hold secrets",
                "Trust approval is sandbox-scoped only",
                "Owner human sign-off not claimed for production",
            ],
        }

    # ── M216 abstraction ─────────────────────────────────────────────────────
    def abstraction(self) -> dict[str, Any]:
        return abstraction_surface()

    # ── M217 registry ────────────────────────────────────────────────────────
    def list_brokers(self) -> dict[str, Any]:
        return {
            "brokers": self.registry.list_brokers(),
            "paper_only": True,
            "labels": {"sandbox_only": "SANDBOX ONLY", "no_live_broker": "NO LIVE BROKER"},
        }

    def get_broker(self, broker_id: str) -> dict[str, Any]:
        b = self.registry.get_broker(broker_id)
        if not b:
            raise BrokerSandboxError("BROKER_NOT_FOUND", broker_id)
        return {"broker": b, "capability": self.registry.get_capability(broker_id).to_public()}

    def list_capabilities(self) -> dict[str, Any]:
        return {
            "capabilities": self.registry.list_capabilities(),
            "connection_invariant": self.registry.assert_all_not_connected(),
            "paper_only": True,
        }

    def refuse_connect(self, broker_id: str) -> dict[str, Any]:
        return self.registry.refuse_connect(broker_id)

    # ── M218 credentials ─────────────────────────────────────────────────────
    def create_credential_ref(self, **kwargs: Any) -> dict[str, Any]:
        try:
            return {"reference": self.credentials.create_reference(**kwargs), "paper_only": True}
        except CredentialTrustError as e:
            raise BrokerSandboxError(e.code, e.message) from e

    def list_credential_refs(self, broker_id: str = "") -> dict[str, Any]:
        return {
            "references": self.credentials.list_references(broker_id),
            "framework": self.credentials.framework_summary(),
            "paper_only": True,
        }

    def revoke_credential_ref(self, ref_id: str, **kwargs: Any) -> dict[str, Any]:
        try:
            return {"reference": self.credentials.revoke(ref_id, **kwargs), "paper_only": True}
        except CredentialTrustError as e:
            raise BrokerSandboxError(e.code, e.message) from e

    def attempt_use_credential(self, ref_id: str) -> dict[str, Any]:
        return self.credentials.attempt_use(ref_id)

    def approve_credential_metadata(self, ref_id: str, **kwargs: Any) -> dict[str, Any]:
        try:
            return {"reference": self.credentials.append_approval(ref_id, **kwargs), "paper_only": True}
        except CredentialTrustError as e:
            raise BrokerSandboxError(e.code, e.message) from e

    # ── M219 emulator ────────────────────────────────────────────────────────
    def emulator_session(self, **kwargs: Any) -> dict[str, Any]:
        return {"session": self.emulator.create_session(**kwargs), "paper_only": True}

    def emulator_place_order(self, session_id: str, **kwargs: Any) -> dict[str, Any]:
        try:
            return {"order": self.emulator.place_order(session_id, **kwargs), "paper_only": True}
        except SandboxBrokerError as e:
            raise BrokerSandboxError(e.code, e.message) from e

    def emulator_orders(self, session_id: str) -> dict[str, Any]:
        return {"orders": self.emulator.list_orders(session_id), "paper_only": True}

    def emulator_set_mode(self, session_id: str, failure_mode: str) -> dict[str, Any]:
        return {"session": self.emulator.set_failure_mode(session_id, failure_mode), "paper_only": True}

    # ── M220 trust ───────────────────────────────────────────────────────────
    def trust_create(self, **kwargs: Any) -> dict[str, Any]:
        try:
            return {"pipeline": self.trust.create_pipeline(**kwargs), "paper_only": True}
        except TrustPipelineError as e:
            raise BrokerSandboxError(e.code, e.message) from e

    def trust_decide(self, pipeline_id: str, **kwargs: Any) -> dict[str, Any]:
        try:
            return {"pipeline": self.trust.decide(pipeline_id, **kwargs), "paper_only": True}
        except TrustPipelineError as e:
            raise BrokerSandboxError(e.code, e.message) from e

    def trust_list(self, broker_id: str = "") -> dict[str, Any]:
        return {"pipelines": self.trust.list_pipelines(broker_id), "paper_only": True}

    def trust_gate(self, pipeline_id: str) -> dict[str, Any]:
        try:
            return self.trust.require_all_stages(pipeline_id)
        except TrustPipelineError as e:
            raise BrokerSandboxError(e.code, e.message) from e

    def trust_auto_activate_refused(self, broker_id: str) -> dict[str, Any]:
        return self.trust.attempt_activate_without_approval(broker_id)

    # ── M221 failure ─────────────────────────────────────────────────────────
    def failure_run(self, scenario: str, **kwargs: Any) -> dict[str, Any]:
        return self.failure.run(scenario, **kwargs)

    def failure_suite(self) -> dict[str, Any]:
        return self.failure.run_suite()

    def failure_scenarios(self) -> dict[str, Any]:
        return {"scenarios": FAILURE_SCENARIOS, "paper_only": True}

    def failure_events(self) -> dict[str, Any]:
        return {"events": self.failure.list_events(), "paper_only": True}

    # ── M222 security ────────────────────────────────────────────────────────
    def security_validate(self) -> dict[str, Any]:
        return self.security.run_all()

    def security_checks(self) -> dict[str, Any]:
        return {"checks": self.security.list_checks(), "paper_only": True}

    # ── M223 control center ──────────────────────────────────────────────────
    def dashboard(self) -> dict[str, Any]:
        return self.control.overview()

    def audit_timeline(self, limit: int = 100) -> dict[str, Any]:
        return {
            "events": self.store.list_audit(limit=limit),
            "labels": self.control.labels(),
            "paper_only": True,
        }


_default: BrokerSandboxService | None = None


def default_broker_sandbox(db_path: str | Path | None = None) -> BrokerSandboxService:
    global _default
    if _default is None:
        _default = BrokerSandboxService(db_path=db_path)
    return _default


def reset_broker_sandbox_for_tests(db_path: str | Path | None = None) -> BrokerSandboxService:
    global _default
    if _default is not None:
        try:
            _default.store.close()
        except Exception:
            pass
    _default = BrokerSandboxService(db_path=db_path)
    return _default


__all__ = [
    "BrokerSandboxService",
    "BrokerSandboxError",
    "default_broker_sandbox",
    "reset_broker_sandbox_for_tests",
    "TERMINAL_VERDICT",
]
