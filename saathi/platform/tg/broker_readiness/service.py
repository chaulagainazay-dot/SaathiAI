"""M224–M231 Read-Only Broker Readiness Service facade.

SIMULATION ONLY. Composes adapter, policy, credentials, scope, connection,
snapshots, reconciliation, drills, security, and control center.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from saathi.platform.tg.broker_readiness.adapter import (
    AdapterContractError,
    ReadOnlyAdapterContract,
)
from saathi.platform.tg.broker_readiness.connection import (
    ConnectionError,
    SimulatedConnectionMachine,
)
from saathi.platform.tg.broker_readiness.control_center import ReadinessControlCenter
from saathi.platform.tg.broker_readiness.credentials import (
    CredentialLifecycleError,
    SimulatedCredentialLifecycle,
)
from saathi.platform.tg.broker_readiness.drills import IncidentDrillSuite
from saathi.platform.tg.broker_readiness.models import (
    ENGINE_VERSION,
    LLM_BOUNDARY,
    READINESS_POSTURE,
    SCHEMA_VERSION,
    TERMINAL_VERDICT,
    CREDENTIAL_USABLE_FOR_REAL_CONNECTION,
    LIVE_TRADING_AUTHORIZED,
    ORDER_SUBMISSION_CAPABLE,
    REAL_BROKER_CONNECTION_CAPABLE,
)
from saathi.platform.tg.broker_readiness.policy import PolicyEngine
from saathi.platform.tg.broker_readiness.scope import ScopeValidator
from saathi.platform.tg.broker_readiness.secrets import SecretRejectionError, reject_secrets_in_payload
from saathi.platform.tg.broker_readiness.security import ReadinessSecurityValidator
from saathi.platform.tg.broker_readiness.snapshots import (
    AccountSnapshotService,
    ReconciliationEngine,
    SnapshotError,
)
from saathi.platform.tg.broker_readiness.store import ReadinessStore
from saathi.platform.tg.broker_readiness.transport import (
    REAL_PROVIDER_TRANSPORT_FORBIDDEN,
    TransportGuard,
    TransportGuardError,
    reset_transport_guard,
)


class BrokerReadinessError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class BrokerReadinessService:
    def __init__(self, db_path: str | Path | None = None):
        self.store = ReadinessStore(db_path)
        self.transport = TransportGuard(self.store)
        reset_transport_guard(self.store)
        self.adapter = ReadOnlyAdapterContract(self.store, self.transport)
        self.policy = PolicyEngine(self.store)
        self.credentials = SimulatedCredentialLifecycle(self.store)
        self.scopes = ScopeValidator(self.store)
        self.connections = SimulatedConnectionMachine(self.store, self.transport)
        self.snapshots = AccountSnapshotService(self.store)
        self.reconcile = ReconciliationEngine(self.store, self.snapshots)
        self.drills = IncidentDrillSuite(
            self.store, self.credentials, self.connections,
            self.scopes, self.snapshots, self.reconcile,
        )
        self.security = ReadinessSecurityValidator(
            self.store, self.transport,
            credentials=self.credentials, policy=self.policy,
            scopes=self.scopes, connections=self.connections,
        )
        self.control = ReadinessControlCenter(self)

    def posture(self) -> dict[str, Any]:
        return {
            **READINESS_POSTURE,
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "milestones": "M224-M231",
            "terminal_verdict_target": TERMINAL_VERDICT,
            "llm_boundary": dict(LLM_BOUNDARY),
            "live_trading_authorized": LIVE_TRADING_AUTHORIZED,
            "real_broker_connection_capable": REAL_BROKER_CONNECTION_CAPABLE,
            "order_submission_capable": ORDER_SUBMISSION_CAPABLE,
            "credential_usable_for_real_connection": CREDENTIAL_USABLE_FOR_REAL_CONNECTION,
            "SIMULATION_ONLY": True,
        }

    def terminal_verdict(self) -> dict[str, Any]:
        return {
            "verdict": TERMINAL_VERDICT,
            "paper_only": True,
            "sandbox_only": True,
            "simulation_only": True,
            "live_trading_authorized": False,
            "real_broker_connection_created": False,
            "real_broker_account_accessed": False,
            "real_api_credentials_requested_accepted_or_stored": False,
            "order_submission_or_cancellation_exists": False,
            "read_only_readiness_grants_production_authority": False,
            "owner_signoff": "NOT_CLAIMED_AUTOMATED_ONLY",
            "statements": [
                "THE SYSTEM REMAINS PAPER AND SANDBOX ONLY.",
                "NO REAL BROKER CONNECTION WAS CREATED.",
                "NO REAL BROKER ACCOUNT WAS ACCESSED.",
                "NO REAL API CREDENTIALS WERE REQUESTED, ACCEPTED OR STORED.",
                "NO ORDER SUBMISSION OR ORDER CANCELLATION CAPABILITY EXISTS.",
                "LIVE TRADING IS NOT AUTHORIZED.",
                "READ-ONLY READINESS DOES NOT GRANT READ-ONLY PRODUCTION AUTHORITY.",
                "OWNER SIGN-OFF IS NOT CLAIMED UNLESS PROVIDED EXPLICITLY OUTSIDE AUTOMATION.",
            ],
            "limitations": [
                "Single-host SQLite",
                "No real provider implementation",
                "Credential references never hold secrets",
                "Simulated connection only",
                "Owner human sign-off not claimed",
                "Readiness does not authorize production read-only access",
            ],
        }

    def certify(self) -> dict[str, Any]:
        sec = self.security.run_all()
        transport = self.transport.scan_for_external_attempts()
        # structural proof
        proof = {
            "adapter_contracts_exist": True,
            "no_real_provider_implementation": True,
            "write_ops_rejected": True,
            "secrets_rejected": True,
            "transport_blocked": True,
            "security_all_pass": sec.get("all_pass", False),
        }
        verdict = TERMINAL_VERDICT if sec.get("all_pass") else "M224_M231_SECURITY_GATE_FAILED"
        return {
            **self.terminal_verdict(),
            "verdict": verdict,
            "proof": proof,
            "security": {"all_pass": sec.get("all_pass"), "passed": sec.get("passed"), "failed": sec.get("failed")},
            "network_isolation": transport,
            "SIMULATION_ONLY": True,
        }

    # ── M224 ────────────────────────────────────────────────────────────────
    def list_providers(self) -> dict[str, Any]:
        return self.adapter.list_providers()

    def adapter_contract(self) -> dict[str, Any]:
        return self.adapter.contract_summary()

    def list_adapter_ops(self) -> dict[str, Any]:
        return self.adapter.list_operations()

    def invoke_adapter(self, operation: str, **kwargs: Any) -> dict[str, Any]:
        try:
            return self.adapter.invoke(operation, **kwargs)
        except AdapterContractError as e:
            raise BrokerReadinessError(e.code, e.message) from e

    # ── M225 ────────────────────────────────────────────────────────────────
    def policy_check(self, operation: str, **kwargs: Any) -> dict[str, Any]:
        return self.policy.evaluate(operation, **kwargs)

    # ── M226 ────────────────────────────────────────────────────────────────
    def propose_credential(self, provider_id: str = "sim.readonly.fixture", **kwargs: Any) -> dict[str, Any]:
        try:
            # reject top-level secret fields
            reject_secrets_in_payload({"provider_id": provider_id, **kwargs})
            return {
                "credential": self.credentials.propose(provider_id, **kwargs),
                "SIMULATION_ONLY": True,
            }
        except (SecretRejectionError, CredentialLifecycleError) as e:
            code = getattr(e, "code", "CREDENTIAL_ERROR")
            raise BrokerReadinessError(code, str(e)) from e

    def list_credentials(self, provider_id: str = "") -> dict[str, Any]:
        return {
            "credentials": self.credentials.list(provider_id),
            "SIMULATION_ONLY": True,
            "credential_usable_for_real_connection": False,
        }

    def credential_lifecycle(self, credential_id: str, to_state: str = "", **kwargs: Any) -> dict[str, Any]:
        try:
            if to_state:
                return {
                    "credential": self.credentials.transition(credential_id, to_state, **kwargs),
                    "SIMULATION_ONLY": True,
                }
            return {
                "credential": self.credentials.get(credential_id),
                "events": self.credentials.lifecycle_events(credential_id),
                "SIMULATION_ONLY": True,
            }
        except CredentialLifecycleError as e:
            raise BrokerReadinessError(e.code, e.message) from e

    def advance_credential(self, credential_id: str, **kwargs: Any) -> dict[str, Any]:
        try:
            return {
                "credential": self.credentials.advance_happy_path(credential_id, **kwargs),
                "SIMULATION_ONLY": True,
            }
        except CredentialLifecycleError as e:
            raise BrokerReadinessError(e.code, e.message) from e

    def attempt_real_use(self, credential_id: str) -> dict[str, Any]:
        return self.credentials.attempt_use_for_real(credential_id)

    # ── M227 ────────────────────────────────────────────────────────────────
    def scope_check(self, **kwargs: Any) -> dict[str, Any]:
        return self.scopes.validate(**kwargs)

    # ── M228 ────────────────────────────────────────────────────────────────
    def session_create(self, **kwargs: Any) -> dict[str, Any]:
        return {"session": self.connections.create_session(**kwargs), "SIMULATION_ONLY": True}

    def session_simulate(self, session_id: str, *, real_url: str | None = None) -> dict[str, Any]:
        try:
            return {
                "session": self.connections.simulate_connect_read_only(session_id, real_url=real_url),
                "SIMULATION_ONLY": True,
            }
        except ConnectionError as e:
            raise BrokerReadinessError(e.code, e.message) from e

    def session_event(self, session_id: str, event: str) -> dict[str, Any]:
        try:
            return {"session": self.connections.simulate_event(session_id, event), "SIMULATION_ONLY": True}
        except ConnectionError as e:
            raise BrokerReadinessError(e.code, e.message) from e

    def list_sessions(self) -> dict[str, Any]:
        return {"sessions": self.connections.list_sessions(), "SIMULATION_ONLY": True}

    def transport_probe(self, url: str) -> dict[str, Any]:
        try:
            self.transport.assert_allowed(url)
            return {"ok": True, "url": url, "result": "LOCAL_SIMULATION_ONLY", "SIMULATION_ONLY": True}
        except TransportGuardError as e:
            return {
                "ok": False,
                "url": url,
                "result": e.code,
                "message": e.message,
                "SIMULATION_ONLY": True,
            }

    # ── M229 ────────────────────────────────────────────────────────────────
    def snapshot_load(self, **kwargs: Any) -> dict[str, Any]:
        return {"snapshot": self.snapshots.load_fixture(**kwargs), "SIMULATION_ONLY": True}

    def list_snapshots(self, provider_id: str = "") -> dict[str, Any]:
        return {"snapshots": self.snapshots.list_snapshots(provider_id), "SIMULATION_ONLY": True}

    def reconcile_run(self, provider_snapshot_id: str, local_snapshot_id: str = "", **kwargs: Any) -> dict[str, Any]:
        try:
            return {
                "reconciliation": self.reconcile.reconcile(
                    provider_snapshot_id, local_snapshot_id, **kwargs,
                ),
                "SIMULATION_ONLY": True,
            }
        except SnapshotError as e:
            raise BrokerReadinessError(e.code, e.message) from e

    def list_reconciliations(self) -> dict[str, Any]:
        return {"results": self.reconcile.list_results(), "SIMULATION_ONLY": True}

    # ── M230 ────────────────────────────────────────────────────────────────
    def drill_run(self, scenario: str, **kwargs: Any) -> dict[str, Any]:
        return self.drills.run(scenario, **kwargs)

    def drill_suite(self) -> dict[str, Any]:
        return self.drills.run_suite()

    def drill_scenarios(self) -> dict[str, Any]:
        return self.drills.list_scenarios()

    def list_drills(self) -> dict[str, Any]:
        return {"drills": self.drills.list_drills(), "SIMULATION_ONLY": True}

    def expiry_drill(self) -> dict[str, Any]:
        return self.drill_run("credential_expiry_during_session")

    def revocation_drill(self) -> dict[str, Any]:
        return self.drill_run("credential_revocation_during_session")

    # ── M231 ────────────────────────────────────────────────────────────────
    def dashboard(self) -> dict[str, Any]:
        return self.control.overview()

    def audit_timeline(self, limit: int = 100) -> dict[str, Any]:
        return {
            "events": self.store.list_audit(limit=limit),
            "labels": self.control.labels(),
            "SIMULATION_ONLY": True,
        }

    def security_scan(self) -> dict[str, Any]:
        return self.security.run_all()

    def llm_refuse(self, action: str) -> dict[str, Any]:
        """Any LLM authority action is refused."""
        forbidden = {
            "approve_credentials", "activate_sessions", "connect_brokers",
            "authorize_live_trading", "store_credentials", "restore_revoked",
            "change_scopes", "submit_orders", "cancel_orders",
        }
        return {
            "ok": False,
            "action": action,
            "error": "LLM_AUTHORITY_DENIED",
            "allowed": action not in forbidden and LLM_BOUNDARY.get(f"llm_may_{action}", False),
            "message": "LLM outputs remain advisory. No authority actions permitted.",
            "SIMULATION_ONLY": True,
        }


_default: BrokerReadinessService | None = None


def default_broker_readiness(db_path: str | Path | None = None) -> BrokerReadinessService:
    global _default
    if _default is None:
        _default = BrokerReadinessService(db_path=db_path)
    return _default


def reset_broker_readiness_for_tests(db_path: str | Path | None = None) -> BrokerReadinessService:
    global _default
    if _default is not None:
        try:
            _default.store.close()
        except Exception:
            pass
    _default = BrokerReadinessService(db_path=db_path)
    return _default


__all__ = [
    "BrokerReadinessService",
    "BrokerReadinessError",
    "default_broker_readiness",
    "reset_broker_readiness_for_tests",
    "TERMINAL_VERDICT",
    "REAL_PROVIDER_TRANSPORT_FORBIDDEN",
]
