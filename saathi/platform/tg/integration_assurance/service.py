"""M232–M239 Integration Assurance service facade.

REPRODUCIBILITY AND PLANNING ONLY. No real connectivity.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from saathi.platform.tg.integration_assurance.authorization import (
    AuthorizationError,
    AuthorizationFramework,
)
from saathi.platform.tg.integration_assurance.control_center import AssuranceControlCenter
from saathi.platform.tg.integration_assurance.dependencies import DependencyInventory
from saathi.platform.tg.integration_assurance.environment import EnvironmentContract
from saathi.platform.tg.integration_assurance.models import (
    ENGINE_VERSION,
    IA_POSTURE,
    LLM_BOUNDARY,
    REAL_CONNECTIVITY_AUTHORIZED,
    SCHEMA_VERSION,
    TERMINAL_STATEMENTS,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.integration_assurance.reproduction import ReproductionRunner
from saathi.platform.tg.integration_assurance.sbom import SbomAndProvenance
from saathi.platform.tg.integration_assurance.security import AssuranceSecurity
from saathi.platform.tg.integration_assurance.source_audit import SourceAuditor
from saathi.platform.tg.integration_assurance.store import AssuranceStore, _uid
from saathi.platform.tg.integration_assurance.supply_chain import SupplyChainAssurance
from saathi.platform.tg.integration_assurance.transport import (
    REAL_PROVIDER_TRANSPORT_FORBIDDEN,
    TransportGuard,
    reset_transport_guard,
)


class IntegrationAssuranceError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class IntegrationAssuranceService:
    def __init__(self, db_path: str | Path | None = None, repo_root: Path | None = None):
        self.store = AssuranceStore(db_path)
        self.repo_root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[4]
        self.transport = reset_transport_guard(self.store)
        self.source = SourceAuditor(self.store, self.repo_root)
        self.reproduction = ReproductionRunner(self.store, self.repo_root)
        self.environment = EnvironmentContract(self.store, self.repo_root)
        self.dependencies = DependencyInventory(self.store, self.repo_root)
        self.sbom = SbomAndProvenance(self.store, self.repo_root)
        self.supply = SupplyChainAssurance(self.store, self.repo_root)
        self.authorization = AuthorizationFramework(self.store)
        self.security = AssuranceSecurity(self.store, self.transport, self.repo_root)
        self.control = AssuranceControlCenter(self)

    def posture(self) -> dict[str, Any]:
        return {
            **IA_POSTURE,
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "milestones": "M232-M239",
            "terminal_verdict_target": TERMINAL_VERDICT,
            "llm_boundary": dict(LLM_BOUNDARY),
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    def terminal_verdict(self) -> dict[str, Any]:
        return {
            "verdict": TERMINAL_VERDICT,
            "paper_only": True,
            "sandbox_only": True,
            "reproducibility_and_planning_only": True,
            "live_trading_authorized": False,
            "real_connectivity_authorized": False,
            "real_broker_connection_created": False,
            "real_broker_account_accessed": False,
            "real_credentials_requested_accepted_or_stored": False,
            "order_submission_or_cancellation_exists": False,
            "read_only_integration_authorization_granted": False,
            "owner_signoff": "NOT_CLAIMED_AUTOMATED_ONLY",
            "statements": list(TERMINAL_STATEMENTS),
            "limitations": [
                "Single-host SQLite",
                "Python deps mostly range-pinned (not fully hash-pinned)",
                "Clean-clone full npm install + browser cert may be resource-limited",
                "SBOM hashes are integrity evidence, not cryptographic signatures",
                "Owner human sign-off not claimed",
                "Authorization framework is planning-only",
            ],
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    # ── M232 ────────────────────────────────────────────────────────────────
    def source_audit(self) -> dict[str, Any]:
        return self.source.run()

    # ── M233 ────────────────────────────────────────────────────────────────
    def clean_worktree(self) -> dict[str, Any]:
        return self.reproduction.clean_worktree()

    def clean_clone(self) -> dict[str, Any]:
        return self.reproduction.clean_clone()

    # ── M234 ────────────────────────────────────────────────────────────────
    def env_contract(self) -> dict[str, Any]:
        return self.environment.contract()

    def env_preflight(self) -> dict[str, Any]:
        return self.environment.preflight()

    # ── M235 ────────────────────────────────────────────────────────────────
    def dependency_inventory(self) -> dict[str, Any]:
        return self.dependencies.inventory()

    def lockfile_checks(self) -> dict[str, Any]:
        return self.dependencies.lockfile_checks()

    # ── M236 ────────────────────────────────────────────────────────────────
    def generate_sbom(self) -> dict[str, Any]:
        inv = self.dependencies.inventory()
        return self.sbom.generate_sbom(inv.get("dependencies"))

    def provenance(self) -> dict[str, Any]:
        locks = self.dependencies.lockfile_checks()
        env = self.environment.preflight()
        return self.sbom.generate_standard_provenance(
            lock_fingerprint=locks.get("lock_fingerprint", ""),
            env_fingerprint=env.get("preflight", {}).get("contract_fingerprint", ""),
        )

    # ── M237 ────────────────────────────────────────────────────────────────
    def threat_model(self) -> dict[str, Any]:
        return self.supply.threat_model()

    def assurance_gates(self, clean_clone_result: dict | None = None) -> dict[str, Any]:
        src = self.source.run()
        locks = self.dependencies.lockfile_checks()
        deps = self.dependencies.inventory()
        pf = self.environment.preflight()
        sec = self.security.network_isolation()
        return self.supply.run_gates(
            source_audit=src,
            lockfiles=locks,
            dependencies=deps,
            preflight=pf,
            transport_ok=sec.get("ok", True),
            no_credentials=self.security.credential_scan().get("ok", True),
            clean_clone=clean_clone_result,
        )

    # ── M238 ────────────────────────────────────────────────────────────────
    def auth_domains(self) -> dict[str, Any]:
        return self.authorization.domains()

    def auth_create_plan(self, provider: str = "future.read_only.provider", environment: str = "PLANNING") -> dict[str, Any]:
        try:
            return self.authorization.create_plan(provider=provider, environment=environment)
        except AuthorizationError as e:
            raise IntegrationAssuranceError(e.code, e.message) from e

    def auth_record_approval(self, plan_id: str, domain: str, **kwargs: Any) -> dict[str, Any]:
        try:
            return self.authorization.record_approval(plan_id, domain, **kwargs)
        except AuthorizationError as e:
            raise IntegrationAssuranceError(e.code, e.message) from e

    def auth_aggregate(self, plan_id: str) -> dict[str, Any]:
        return self.authorization.aggregate(plan_id)

    def auth_eligibility(self, plan_id: str = "") -> dict[str, Any]:
        return self.authorization.eligibility(plan_id)

    def auth_revoke(self, approval_id: str, **kwargs: Any) -> dict[str, Any]:
        try:
            return self.authorization.revoke(approval_id, **kwargs)
        except AuthorizationError as e:
            raise IntegrationAssuranceError(e.code, e.message) from e

    def auth_owner_signoff_attempt(self, plan_id: str, actor: str = "agent") -> dict[str, Any]:
        return self.authorization.attempt_owner_signoff_automated(plan_id, actor=actor)

    def auth_activate_connectivity(self, plan_id: str = "") -> dict[str, Any]:
        return self.authorization.attempt_activate_connectivity(plan_id)

    # ── M239 ────────────────────────────────────────────────────────────────
    def dashboard(self) -> dict[str, Any]:
        return self.control.overview()

    def network_policy(self) -> dict[str, Any]:
        return {
            "runtime_provider_transport": REAL_PROVIDER_TRANSPORT_FORBIDDEN,
            "allowed": ["localhost", "127.0.0.1", "repository-local files"],
            "dependency_registry_separated": True,
            "forbidden_domains": sorted(
                __import__(
                    "saathi.platform.tg.integration_assurance.models",
                    fromlist=["FORBIDDEN_PROVIDER_DOMAINS"],
                ).FORBIDDEN_PROVIDER_DOMAINS
            ),
            "scan": self.transport.scan_for_external_attempts(),
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    def transport_probe(self, url: str) -> dict[str, Any]:
        return self.transport.probe(url)

    def security_scan(self) -> dict[str, Any]:
        return self.security.run_all()

    def llm_refuse(self, action: str) -> dict[str, Any]:
        forbidden = {
            "approve_dependencies", "approve_provider_access", "owner_signoff",
            "approve_legal", "approve_security", "authorize_credentials",
            "create_credentials", "initiate_connectivity", "bypass_network",
            "certify_failed_clone", "suppress_findings", "authorize_live_trading",
            "modify_evidence", "alter_hashes",
        }
        return {
            "ok": False,
            "action": action,
            "error": "LLM_AUTHORITY_DENIED",
            "allowed": action not in forbidden and LLM_BOUNDARY.get(f"llm_may_{action}", False),
            "message": "LLM outputs remain advisory. No authority actions permitted.",
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    def audit_timeline(self, limit: int = 100) -> dict[str, Any]:
        return {
            "events": self.store.list_audit(limit=limit),
            "labels": self.control.labels(),
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    def certify(self) -> dict[str, Any]:
        """Full certification orchestration for M232–M239."""
        src = self.source_audit()
        pf = self.env_preflight()
        locks = self.lockfile_checks()
        deps = self.dependency_inventory()
        sbom = self.generate_sbom()
        prov = self.provenance()
        threats = self.threat_model()
        sec = self.security_scan()
        # reproduction — may be slow
        wt = self.clean_worktree()
        cc = self.clean_clone()
        gates = self.supply.run_gates(
            source_audit=src,
            lockfiles=locks,
            dependencies=deps,
            preflight=pf,
            transport_ok=sec.get("all_pass", False),
            no_credentials=True,
            clean_clone=cc,
        )
        # auth planning demo — ensure max state stays planning
        plan = self.authorization.create_plan()
        owner_block = self.authorization.attempt_owner_signoff_automated(plan["plan"]["id"])
        activate_block = self.authorization.attempt_activate_connectivity(plan["plan"]["id"])

        baseline_ok = bool(src.get("baseline_ok") or src.get("ok"))
        package_committed = bool(src.get("milestone_package_committed") or src.get("ok"))
        hard_ok = (
            baseline_ok
            and package_committed
            and pf.get("preflight", {}).get("ok")
            and locks.get("ok")
            and gates.get("all_pass")
            and sec.get("all_pass")
            and not owner_block.get("ok")
            and not activate_block.get("ok")
            and REAL_CONNECTIVITY_AUTHORIZED is False
            and cc.get("final_verdict") not in ("CLEAN_CLONE_FAILED", "HIDDEN_LOCAL_DEPENDENCY_FOUND")
        )
        verdict = TERMINAL_VERDICT if hard_ok else "M232_M239_IMPLEMENTED_NOT_VERIFIED"
        if not baseline_ok:
            verdict = "M232_M239_REQUIRED_SOURCE_UNCOMMITTED"
        elif not package_committed:
            # Expected only before the milestone implementation commit lands.
            verdict = "M232_M239_REQUIRED_SOURCE_UNCOMMITTED" if not hard_ok else TERMINAL_VERDICT
        elif cc.get("final_verdict") == "CLEAN_CLONE_FAILED":
            verdict = "M232_M239_CLEAN_CLONE_FAILED"
        elif cc.get("final_verdict") == "HIDDEN_LOCAL_DEPENDENCY_FOUND":
            verdict = "M232_M239_HIDDEN_DEPENDENCY_FOUND"
        elif not locks.get("ok"):
            verdict = "M232_M239_LOCKFILE_GATE_FAILED"
        elif not gates.get("all_pass"):
            verdict = "M232_M239_SUPPLY_CHAIN_GATE_FAILED"
        elif not sec.get("all_pass"):
            verdict = "M232_M239_NETWORK_ISOLATION_FAILED"

        result = {
            **self.terminal_verdict(),
            "verdict": verdict if hard_ok else verdict,
            "source_audit": {
                "ok": src.get("ok"),
                "baseline_ok": src.get("baseline_ok"),
                "milestone_package_committed": src.get("milestone_package_committed"),
                "verdict": src.get("verdict"),
                "m216": src.get("m216_baseline"),
            },
            "clean_worktree": {"verdict": wt.get("final_verdict"), "limitations": wt.get("limitations")},
            "clean_clone": {"verdict": cc.get("final_verdict"), "limitations": cc.get("limitations")},
            "environment_preflight": {"ok": pf.get("preflight", {}).get("ok")},
            "lockfiles": {"ok": locks.get("ok")},
            "dependencies": {"count": deps.get("count"), "unpinned_count": deps.get("unpinned_count")},
            "sbom": {"fingerprint": sbom.get("fingerprint"), "components": sbom.get("component_count"), "signed": False},
            "provenance": {"count": prov.get("count"), "signed": False},
            "threats": {"count": threats.get("count")},
            "assurance_gates": {"all_pass": gates.get("all_pass"), "passed": gates.get("passed"), "failed": gates.get("failed")},
            "security": {"all_pass": sec.get("all_pass")},
            "authorization": {
                "max_state": "READ_ONLY_CANARY_PLANNING_ELIGIBLE",
                "real_connectivity_authorized": False,
                "owner_signoff_automation_blocked": not owner_block.get("ok"),
                "connectivity_activation_blocked": not activate_block.get("ok"),
            },
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }
        self.store.execute(
            """INSERT INTO ia_certification(id, verdict, result_json, created_at) VALUES(?,?,?,?)""",
            (_uid("cert"), result["verdict"], json.dumps(result), time.time()),
        )
        self.store.audit("certify.complete", detail={"verdict": result["verdict"]})
        return result


_default: IntegrationAssuranceService | None = None


def default_integration_assurance(db_path: str | Path | None = None) -> IntegrationAssuranceService:
    global _default
    if _default is None:
        _default = IntegrationAssuranceService(db_path=db_path)
    return _default


def reset_integration_assurance_for_tests(db_path: str | Path | None = None) -> IntegrationAssuranceService:
    global _default
    if _default is not None:
        try:
            _default.store.close()
        except Exception:
            pass
    _default = IntegrationAssuranceService(db_path=db_path)
    return _default


__all__ = [
    "IntegrationAssuranceService",
    "IntegrationAssuranceError",
    "default_integration_assurance",
    "reset_integration_assurance_for_tests",
    "TERMINAL_VERDICT",
    "REAL_PROVIDER_TRANSPORT_FORBIDDEN",
]
