"""R2 trunk convergence — architecture invariant attestation.

A convergence merges two independently developed lines into one trunk. The risk
that matters is not a failing test; it is an authority boundary that quietly
relaxed because two branches disagreed about it and the merge picked one. Every
invariant this repository refuses to cross is asserted here, in one place, so
the attestation in the convergence manifest is produced by running code rather
than by reading it.

These are not new controls. Each is enforced somewhere in the system already and
covered by its own milestone suite. What this file adds is a single executable
statement of the R2 exit conditions that fails loudly if convergence, or any
later change, moves one of them.
"""
from __future__ import annotations

import pathlib
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


class TestSingleExecutionBoundary:
    """Exactly one ExecutionGateway, and no path around it."""

    def test_exactly_one_execution_gateway_class(self):
        hits = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "grep", "-n", "^class ExecutionGateway", "--", "saathi/"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip().splitlines()
        defining = [h for h in hits if "ExecutionGatewayException" not in h]
        assert len(defining) == 1, f"expected one ExecutionGateway, found: {defining}"
        assert "saathi/execution/gateway.py" in defining[0]

    def test_gateway_is_importable_and_singular(self):
        from saathi.execution.gateway import ExecutionGateway

        assert ExecutionGateway.__module__ == "saathi.execution.gateway"


class TestTradingGuardianAuthority:
    """The Guardian's posture is the product's promise. None of it may drift."""

    @pytest.fixture(scope="class")
    def posture(self):
        from saathi.platform.tg.service import TradingGuardianService

        return TradingGuardianService().posture()

    @pytest.mark.parametrize(
        "key",
        ["live_trading_authorized", "live_order_capable", "broker_credential_support",
         "leverage_allowed", "margin_allowed"],
    )
    def test_prohibited_capability_is_false(self, posture, key):
        assert posture[key] is False, f"Trading Guardian posture.{key} must stay False"

    def test_paper_only(self, posture):
        assert posture["paper_only"] is True
        assert posture["funds_label"] == "SIMULATED"

    def test_approval_is_required(self, posture):
        assert posture["require_approval"] is True

    def test_kill_switch_present(self, posture):
        assert "kill_switch" in posture and posture["kill_switch"] is not None

    def test_execution_path_runs_through_approval_and_gateway(self, posture):
        path = posture["execution_path"]
        assert "ApprovalCenter" in path
        assert "ExecutionGateway" in path

    @pytest.mark.parametrize(
        "boundary",
        ["may_size_positions", "may_approve", "may_override_policy", "may_override_kill_switch"],
    )
    def test_no_model_gains_hard_authority(self, posture, boundary):
        assert posture["llm_boundary"][boundary] is False, (
            f"a provider/model must not gain {boundary}"
        )


class TestDefaultPolicyProhibitions:
    def test_default_policy_forbids_leverage_margin_shorting_and_live(self):
        from saathi.platform.tg.policy import DEFAULT_POLICY

        assert DEFAULT_POLICY.leverage_allowed is False
        assert DEFAULT_POLICY.margin_allowed is False
        assert DEFAULT_POLICY.shorting_allowed is False
        assert DEFAULT_POLICY.martingale_allowed is False
        assert DEFAULT_POLICY.live_trading_allowed is False

    def test_default_policy_requires_approval_and_is_advisory(self):
        from saathi.platform.tg.domain import AuthorityMode
        from saathi.platform.tg.policy import DEFAULT_POLICY

        assert DEFAULT_POLICY.require_approval is True
        assert DEFAULT_POLICY.authority_mode is AuthorityMode.ADVISORY


class TestBrokerConnectivityAuthority:
    @pytest.fixture(scope="class")
    def readiness(self):
        from saathi.platform.tg.broker_readiness.service import BrokerReadinessService

        return BrokerReadinessService().posture()

    @pytest.mark.parametrize(
        "key",
        ["live_trading_authorized", "real_broker_connection_capable",
         "order_submission_capable", "credential_usable_for_real_connection"],
    )
    def test_broker_capability_is_false(self, readiness, key):
        assert readiness[key] is False

    def test_simulation_only(self, readiness):
        assert readiness["SIMULATION_ONLY"] is True

    def test_terminal_verdict_denies_every_live_path(self):
        from saathi.platform.tg.broker_readiness.service import BrokerReadinessService

        verdict = BrokerReadinessService().terminal_verdict()
        for key in [
            "live_trading_authorized",
            "real_broker_connection_created",
            "real_broker_account_accessed",
            "real_api_credentials_requested_accepted_or_stored",
            "order_submission_or_cancellation_exists",
            "read_only_readiness_grants_production_authority",
        ]:
            assert verdict[key] is False, f"{key} must stay False"


class TestWithdrawalAuthority:
    def test_withdrawals_exist_only_as_simulation(self):
        from saathi.platform.fund_ledger.models import EventType

        names = {e.name for e in EventType}
        withdrawal_names = {n for n in names if "WITHDRAW" in n}
        assert withdrawal_names, "the ledger must model withdrawals to refuse them"
        assert withdrawal_names == {"WITHDRAWAL_SIM"}, (
            f"a non-simulated withdrawal type appeared: {withdrawal_names}"
        )


class TestAuthenticationIsNotOptional:
    """Protected routes stay protected, and CORS stays outermost."""

    def test_cors_middleware_is_outermost(self):
        from saathi.server import app

        names = [m.cls.__name__ for m in app.user_middleware]
        assert names[0] == "CORSMiddleware"

    def test_auth_gate_has_no_method_bypass(self):
        import inspect

        from saathi import server

        source = inspect.getsource(server._auth)
        assert 'request.method == "OPTIONS"' not in source

    @pytest.mark.parametrize(
        "path",
        ["/api/v1/auth/sessions", "/api/v1/security/timeline", "/api/v1/security/tokens"],
    )
    def test_protected_route_rejects_anonymous_request(self, path):
        from fastapi.testclient import TestClient

        from saathi.server import app

        assert TestClient(app).get(path).status_code == 401


class TestNoCredentialsCommitted:
    """A .env must never be tracked, whatever else changes."""

    def test_env_file_is_not_tracked(self):
        tracked = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.splitlines()
        offenders = [
            p for p in tracked
            if pathlib.PurePath(p).name == ".env" or pathlib.PurePath(p).name.startswith(".env.")
            if not pathlib.PurePath(p).name.endswith((".example", ".template", ".sample"))
        ]
        assert offenders == [], f"credential files are tracked: {offenders}"

    def test_env_is_git_ignored(self):
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "check-ignore", "-q", ".env"], check=False
        )
        assert result.returncode == 0


class TestSafetyControlsPresent:
    def test_kill_switch_store_exists(self):
        from saathi.platform.tg.kill_switch import KillSwitchStore

        assert KillSwitchStore().status() is not None

    def test_circuit_breakers_exist(self):
        from saathi.platform.safety import evaluator  # noqa: F401

        assert hasattr(evaluator, "__file__")

    def test_reconciliation_is_reachable(self):
        from saathi.platform.tg import recovery  # noqa: F401

        assert hasattr(recovery, "__file__")


class TestDeterministicEnvironment:
    def test_saathi_resolves_to_this_checkout(self):
        import saathi

        resolved = pathlib.Path(saathi.__file__).resolve()
        assert resolved.relative_to(REPO_ROOT).parts[0] == "saathi"

    def test_runtime_provenance_reports_this_checkout(self):
        from saathi.provenance import runtime_provenance

        assert runtime_provenance("development")["worktreePath"] == str(REPO_ROOT)
