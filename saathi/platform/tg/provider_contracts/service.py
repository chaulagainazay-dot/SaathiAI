"""M320–M327 provider contracts composed into connectivity governance."""
from __future__ import annotations

import ast
from pathlib import Path
from threading import RLock
from typing import Any, Mapping

from saathi.platform.tg.connectivity_governance.service import (
    ConnectivityGovernanceService,
    default_connectivity_governance,
    reset_connectivity_governance_for_tests,
)
from saathi.platform.tg.provider_contracts.capabilities import (
    capability_catalog,
    negotiate_capabilities,
)
from saathi.platform.tg.provider_contracts.errors import (
    ProviderContractError,
    ProviderErrorCode,
    normalize_error,
)
from saathi.platform.tg.provider_contracts.fixtures import FixtureCatalog
from saathi.platform.tg.provider_contracts.models import (
    AUTHORITY_LOCKS,
    BOUNDARY_VALUES,
    BROWSER_CERT_VERDICT,
    CURRENT_MATURITY,
    ENGINE_VERSION,
    MAX_STATE,
    MOCK_PROVIDER_ID,
    REPLAY_PROVIDER_ID,
    SCHEMA_VERSION,
    TERMINAL_STATEMENTS,
    TERMINAL_VERDICT,
    SessionState,
    authority_locks_intact,
)
from saathi.platform.tg.provider_contracts.provider import (
    DeterministicMockProvider,
    DeterministicReplayProvider,
)
from saathi.platform.tg.provider_contracts.schema import validate_request_payload

FORBIDDEN_NETWORK_IMPORTS = frozenset({
    "aiohttp",
    "httpx",
    "requests",
    "socket",
    "urllib",
    "websocket",
    "websockets",
})


class ProviderContractService:
    def __init__(
        self,
        governance: ConnectivityGovernanceService | None = None,
        repo_root: Path | None = None,
    ):
        self.governance = governance or default_connectivity_governance()
        self.repo_root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[4]
        catalog = FixtureCatalog()
        self.mock_provider = DeterministicMockProvider(catalog)
        self.replay_provider = DeterministicReplayProvider(catalog)
        self._providers = {
            MOCK_PROVIDER_ID: self.mock_provider,
            REPLAY_PROVIDER_ID: self.replay_provider,
        }

    def posture(self) -> dict[str, Any]:
        governance_provider = self.governance.get_provider("prov_mock_contract")
        return {
            "ok": True,
            "milestones": "M320-M327",
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "verdict_target": TERMINAL_VERDICT,
            "browser_verdict_target": BROWSER_CERT_VERDICT,
            "max_state": MAX_STATE,
            "current_maturity": CURRENT_MATURITY,
            "mode": "CREDENTIALLESS_OFFLINE_PROVIDER_CONTRACTS",
            "governance_binding": {
                "provider_id": "prov_mock_contract",
                "registered": governance_provider.get("ok") is True,
                "governance_status": (governance_provider.get("provider") or {}).get("governance_status"),
                "connected": False,
            },
            "transport_allowlist": ["mock", "replay"],
            "transport_blocklist": ["http", "https", "websocket", "broker_sdk"],
            "statements": list(TERMINAL_STATEMENTS),
            **BOUNDARY_VALUES,
        }

    def list_providers(self) -> dict[str, Any]:
        providers = []
        for provider in self._providers.values():
            providers.append({
                **provider.descriptor.to_dict(),
                "session": provider.session_snapshot(),
                "transport_contract": provider.transport_snapshot(),
                "governance_registry_binding": "prov_mock_contract",
            })
        return {
            "ok": True,
            "count": len(providers),
            "providers": providers,
            "any_real": False,
            "any_connected": False,
            "any_authenticated": False,
            **AUTHORITY_LOCKS,
        }

    def get_provider(self, provider_id: str) -> dict[str, Any]:
        provider = self._providers.get(provider_id)
        if provider is None:
            raise ProviderContractError(
                ProviderErrorCode.UNAVAILABLE,
                "Offline provider is unavailable",
                details={"provider_id": provider_id},
            )
        return {
            "ok": True,
            "provider": {
                **provider.descriptor.to_dict(),
                "session": provider.session_snapshot(),
                "transport_contract": provider.transport_snapshot(),
            },
            **AUTHORITY_LOCKS,
        }

    def capabilities(self) -> dict[str, Any]:
        return {
            **capability_catalog(),
            "providers": {
                provider_id: [capability.value for capability in provider.descriptor.capabilities]
                for provider_id, provider in self._providers.items()
            },
            **AUTHORITY_LOCKS,
        }

    def negotiate(self, provider_id: str, requested: list[str]) -> dict[str, Any]:
        result = negotiate_capabilities(provider_id, requested)
        self.governance.store.audit(
            "provider_capability_negotiate",
            "provider_contracts",
            provider_id,
            {"requested": requested, "granted": result["granted"], "executes": False},
        )
        return {**result, **AUTHORITY_LOCKS}

    def sessions(self) -> dict[str, Any]:
        return {
            "ok": True,
            "states": [state.value for state in SessionState],
            "authentication_state_exists": False,
            "sessions": [
                provider.session_snapshot()
                for provider in self._providers.values()
            ],
            **AUTHORITY_LOCKS,
        }

    def replay_fixtures(self) -> dict[str, Any]:
        fixtures = self.replay_provider.replay_manifest()
        return {
            "ok": True,
            "count": len(fixtures),
            "fixtures": fixtures,
            "deterministic": True,
            "recorded_offline": True,
            "network_capture": False,
            **AUTHORITY_LOCKS,
        }

    def dispatch(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        request = validate_request_payload(payload)
        provider = self._providers.get(request.provider_id)
        if provider is None:
            raise ProviderContractError(
                ProviderErrorCode.UNAVAILABLE,
                "Offline provider is unavailable",
                details={"provider_id": request.provider_id},
            )
        response = provider.request(request)
        self.governance.store.audit(
            "provider_offline_request",
            "provider_contracts",
            request.provider_id,
            {
                "operation": request.operation,
                "request_id": request.request_id,
                "request_fingerprint": request.fingerprint,
                "transport": provider.transport_kind.value,
                "fixture_id": response.fixture_id,
                "response_hash": response.response_hash,
            },
        )
        return {"ok": True, "response": response.to_dict(), **AUTHORITY_LOCKS}

    def request(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            return self.dispatch(payload)
        except Exception as exc:
            error = normalize_error(exc)
            return {
                "ok": False,
                "status": "error",
                "error": error.to_dict(),
                "schema_version": SCHEMA_VERSION,
                "real_connectivity": False,
                **AUTHORITY_LOCKS,
            }

    def mock_quote(self) -> dict[str, Any]:
        return self.dispatch({
            "provider_id": MOCK_PROVIDER_ID,
            "operation": "quotes.get",
            "params": {"symbol": "AAPL"},
            "idempotency_key": "cli:mock:quote:AAPL:v1",
        })

    def replay_quote(self) -> dict[str, Any]:
        return self.dispatch({
            "provider_id": REPLAY_PROVIDER_ID,
            "operation": "quotes.get",
            "params": {"symbol": "AAPL"},
            "idempotency_key": "cli:replay:quote:AAPL:v1",
        })

    def dashboard(self) -> dict[str, Any]:
        providers = self.list_providers()
        capabilities = self.capabilities()
        fixtures = self.replay_fixtures()
        return {
            "ok": True,
            "title": "Credentialless Provider Contracts",
            "subtitle": "Deterministic mock and replay connectivity only",
            "verdict_target": TERMINAL_VERDICT,
            "max_state": MAX_STATE,
            "current_maturity": CURRENT_MATURITY,
            "overview": {
                "provider_count": providers["count"],
                "mock_transports": 1,
                "replay_transports": 1,
                "network_transports": 0,
                "replay_fixture_count": fixtures["count"],
                "supported_offline_capability_count": len(capabilities["supported_offline"]),
                "real_connections": 0,
                "authenticated_sessions": 0,
                "accounts_accessed": 0,
                "orders_submitted": 0,
            },
            "allowed_ui_actions": [
                "load_provider_contracts",
                "negotiate_offline_capabilities",
                "preview_deterministic_mock_fixture",
                "preview_recorded_replay_fixture",
                "run_offline_certification",
            ],
            "forbidden_ui_controls": [
                "credential_input",
                "oauth_button",
                "login_button",
                "real_provider_connect_button",
                "account_selector",
                "order_form",
                "canary_activation",
                "deployment_control",
            ],
            "statements": list(TERMINAL_STATEMENTS),
            **BOUNDARY_VALUES,
        }

    def transport_isolation_scan(self) -> dict[str, Any]:
        package_dir = Path(__file__).resolve().parent
        findings = []
        inspected = []
        for path in sorted(package_dir.glob("*.py")):
            inspected.append(path.name)
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                modules: list[str] = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module]
                for module in modules:
                    root = module.split(".", 1)[0]
                    if root in FORBIDDEN_NETWORK_IMPORTS:
                        findings.append({"file": path.name, "module": module})
        return {
            "ok": not findings,
            "findings": findings,
            "inspected_files": inspected,
            "allowed_transports": ["mock", "replay"],
            "network_transport_classes": 0,
            "broker_sdk_imports": 0,
            **AUTHORITY_LOCKS,
        }

    def security_scan(self) -> dict[str, Any]:
        isolation = self.transport_isolation_scan()
        governance_security = self.governance.security_scan()
        providers = self.list_providers()
        findings = []
        if not authority_locks_intact():
            findings.append("authority_lock_failed")
        if not isolation["ok"]:
            findings.append("network_import_detected")
        if not governance_security.get("ok"):
            findings.append("governance_security_failed")
        if providers["any_connected"] or providers["any_authenticated"] or providers["any_real"]:
            findings.append("provider_boundary_failed")
        return {
            "ok": not findings,
            "findings": findings,
            "transport_isolation": isolation,
            "governance_security_ok": governance_security.get("ok") is True,
            "authority_locks_intact": authority_locks_intact(),
            **BOUNDARY_VALUES,
        }

    def maturity(self) -> dict[str, Any]:
        return {
            "ok": True,
            "current": CURRENT_MATURITY,
            "max_state": MAX_STATE,
            "governance_dependency": "GOVERNANCE_ONLY_CERTIFIED",
            "mock_provider_ready": True,
            "replay_provider_ready": True,
            "real_provider_ready": False,
            "can_advance_automatically": False,
            "next_state_requires_new_human_authority": True,
            **AUTHORITY_LOCKS,
        }

    def evidence_bundle(self) -> dict[str, Any]:
        return {
            "ok": True,
            "posture": self.posture(),
            "providers": self.list_providers(),
            "capabilities": self.capabilities(),
            "sessions": self.sessions(),
            "replay_fixtures": self.replay_fixtures(),
            "security": self.security_scan(),
            "maturity": self.maturity(),
            "governance_audit": self.governance.store.list_audit(50),
            **AUTHORITY_LOCKS,
        }

    def certify(self) -> dict[str, Any]:
        from saathi.platform.tg.provider_contracts.certification import (
            certify_provider_contracts,
        )
        return certify_provider_contracts(self)


_default: ProviderContractService | None = None
_default_lock = RLock()


def default_provider_contracts() -> ProviderContractService:
    global _default
    with _default_lock:
        if _default is None:
            _default = ProviderContractService()
        return _default


def reset_provider_contracts_for_tests(
    db_path: str | Path | None = None,
) -> ProviderContractService:
    global _default
    governance = reset_connectivity_governance_for_tests(db_path=db_path)
    with _default_lock:
        _default = ProviderContractService(governance=governance)
        return _default
