"""M15.1 integration funnel, migration scan, credential hardening, failure paths,
backup preservation."""
import tempfile

import pytest

from saathi.connectors.platform import store as S
from saathi.connectors.platform import integration as I
from saathi.connectors.platform import migration as M
from saathi.connectors.platform import credentials as C
from saathi.connectors.platform.execution import ExecutionEngine, ExecRequest
from saathi.connectors.platform.credentials import (
    new_ref, resolve_for_account, CredentialScopeError,
)


@pytest.fixture
def eng():
    st = S.ConnectorStore(tempfile.mktemp(suffix=".db"))
    return ExecutionEngine(store=st), st


# ── integration funnel (Chat/Agent/CEO/Voice all use this) ──────────────────
def test_funnel_routes_through_gateway(eng):
    e, st = eng
    aid = st.add_account(owner="ajay", connector_id="github", label="g", state="healthy")
    r = I.run(owner="ajay", tool_id="github.list_issues", account_id=aid,
              args={"_fixture": "success"}, engine=e)
    assert r["status"] == "success" and "gateway_ref" in r["provenance"]


def test_agent_cannot_self_approve(eng):
    e, st = eng
    aid = st.add_account(owner="ajay", connector_id="github", label="g", state="healthy")
    # agent-originated side-effect with no bound approval → still blocked
    r = I.run(owner="ajay", tool_id="github.create_issue", account_id=aid,
              args={"title": "x"}, actor_type="agent", engine=e)
    assert r["status"] == "approval_required"


def test_describe_action_surfaces_risk():
    d = I.describe_action(tool_id="deploy.deploy_to_production", account_id="a",
                          args={}, owner="ajay")
    assert d["manual_only"] is True and d["requires_approval"] is True


def test_ceo_evidence_tier_never_fakes_success():
    assert I.ceo_evidence_tier({"status": "failed"}) == "unavailable"
    assert I.ceo_evidence_tier({"status": "success"}) == "verified"
    assert I.ceo_evidence_tier({"status": "uncertain"}) == "uncertain"


# ── migration + direct-call scan ────────────────────────────────────────────
def test_no_direct_provider_calls_in_platform():
    assert M.scan_direct_calls() == []


def test_migration_ledger_present():
    s = M.migration_summary()
    assert s["total"] >= 4 and "migrated" in s["by_status"]


# ── credential hardening ────────────────────────────────────────────────────
def test_credential_scope_mismatch_rejected():
    ref = new_ref(connector_id="github", scope="user:ajay", backend="env",
                  backend_key="X_TOK")
    acct = {"owner": "ajay", "connector_id": "github"}
    # wrong connector
    with pytest.raises(CredentialScopeError):
        resolve_for_account(account=acct, ref=ref, expected_connector="gmail", owner="ajay")
    # wrong owner
    with pytest.raises(CredentialScopeError):
        resolve_for_account(account=acct, ref=ref, expected_connector="github", owner="mallory")


def test_credential_revoked_fails(monkeypatch):
    ref = new_ref(connector_id="github", scope="user:ajay", backend="env",
                  backend_key="X_TOK")
    ref.status = C.CredStatus.REVOKED.value
    acct = {"owner": "ajay", "connector_id": "github"}
    with pytest.raises(C.SecretUnavailable):
        resolve_for_account(account=acct, ref=ref, expected_connector="github", owner="ajay")


# ── failure paths (deterministic, honest classification) ────────────────────
@pytest.mark.parametrize("fixture,status", [
    ("auth_fail", "failed"), ("permission_fail", "failed"), ("timeout", "failed"),
    ("rate_limit", "failed"), ("malformed", "failed"), ("uncertain", "uncertain"),
])
def test_failure_paths_typed_and_not_success(eng, fixture, status):
    e, st = eng
    aid = st.add_account(owner="ajay", connector_id="github", label="g", state="healthy")
    r = e.execute(ExecRequest(owner="ajay", tool_id="github.list_issues",
                              account_id=aid, args={"_fixture": fixture}))
    assert r.status == status
    assert r.status not in ("success", "partial")
    assert r.errors and "class" in r.errors[0]


def test_expired_account_cannot_execute(eng):
    e, st = eng
    aid = st.add_account(owner="ajay", connector_id="github", label="g", state="expired")
    r = e.execute(ExecRequest(owner="ajay", tool_id="github.list_issues",
                              account_id=aid, args={"_fixture": "success"}))
    assert r.status == "failed"


# ── backup preservation (references, not secrets) ───────────────────────────
def test_backup_preserves_references_not_secrets(eng, tmp_path):
    e, st = eng
    ref = new_ref(connector_id="github", scope="user:ajay", backend="env",
                  backend_key="GITHUB_TOKEN")
    st.put_cred_ref(ref)
    aid = st.add_account(owner="ajay", connector_id="github", label="g",
                         cred_ref_id=ref.ref_id, state="healthy")
    e.execute(ExecRequest(owner="ajay", tool_id="github.list_issues",
                          account_id=aid, args={"_fixture": "success"}))
    # reference row holds only the env var NAME, never a value
    row = st.get_cred_ref(ref.ref_id)
    assert row["backend_key"] == "GITHUB_TOKEN"
    assert "value" not in row
    # execution history preserved
    assert len(st.list_executions("ajay")) >= 1
