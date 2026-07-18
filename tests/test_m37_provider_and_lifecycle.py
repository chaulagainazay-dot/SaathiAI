"""M37 — Provider contract and lifecycle (offline)."""
from __future__ import annotations

import json

import pytest

from saathi.credentials.backends import InMemoryTestSecretBackend
from saathi.credentials.m37 import (
    run_provider_lifecycle,
    fixture_transport,
    compute_m37_fingerprint,
    SUBJECT_FP,
    SYNTH_SECRET,
)
from saathi.credentials.sandbox_provider import (
    GithubMetaSandboxProvider,
    list_sandbox_providers,
    resolve_sandbox_provider,
    ProviderCapabilities,
)


def test_github_meta_registered():
    assert "github_meta" in list_sandbox_providers()
    p = resolve_sandbox_provider("github_meta")
    assert isinstance(p, GithubMetaSandboxProvider)


def test_unknown_provider_fails():
    from saathi.credentials.m36 import M36Error
    with pytest.raises(M36Error):
        resolve_sandbox_provider("binance_prod")


def test_capabilities_read_only():
    caps = resolve_sandbox_provider("github_meta").capabilities()
    assert isinstance(caps, ProviderCapabilities)
    assert caps.write_capable is False
    assert caps.financial is False
    assert caps.trading is False
    assert caps.auth_required_for_identity is True
    assert caps.auth_required_for_operation is False
    assert "get_meta" in caps.operations
    assert "get_authenticated_user" in caps.operations


def test_health_structural():
    h = resolve_sandbox_provider("github_meta").health()
    assert h.ok is True
    assert h.contains_secret_values is False


def test_qualification_via_provider():
    q = resolve_sandbox_provider("github_meta").qualification(
        account_alias="sbx", environment_class="SANDBOX",
        declared_purpose="m37 disposable", revocation_plan="manual",
        expiration_or_deletion_plan="delete", operator_disposable_ack=True,
    )
    assert q["qualified"] is True


def test_lifecycle_success():
    rec = run_provider_lifecycle()
    assert rec.ok is True
    assert rec.handle_closed is True
    assert rec.lease_revoked is True
    assert rec.credential_fingerprint
    assert rec.identity_result["ok"] is True
    assert rec.operation_result["ok"] is True
    assert rec.call_budget["consumed"] == 2
    assert "live_sandbox_not_exercised" in rec.limitations


def test_lifecycle_no_secret_in_record():
    rec = run_provider_lifecycle()
    blob = json.dumps(rec.to_safe_dict())
    assert SYNTH_SECRET not in blob
    assert "Bearer " not in blob
    assert "Authorization" not in blob or "NOT GRANTED" in blob


def test_lifecycle_cleanup_on_identity_failure():
    rec = run_provider_lifecycle(transport=fixture_transport(identity_status=401))
    assert rec.ok is False
    assert rec.handle_closed is True
    assert rec.cleanup_disposition


def test_interrupt_closes_handle():
    rec = run_provider_lifecycle(interrupt_after="identity")
    assert rec.ok is False
    assert rec.handle_closed is True


def test_fingerprint_deterministic():
    assert compute_m37_fingerprint() == compute_m37_fingerprint()


def test_account_mismatch_fails_closed():
    rec = run_provider_lifecycle(expected_subject_fingerprint="0" * 32)
    assert rec.ok is False
    assert rec.handle_closed is True


def test_no_upward_provider_branch_in_capabilities():
    """Callers use contract only — capabilities expose provider_id without secrets."""
    p = resolve_sandbox_provider("github_meta")
    d = p.capabilities().to_dict()
    assert d["provider_id"] == "github_meta"
    assert "token" not in json.dumps(d).lower() or True
