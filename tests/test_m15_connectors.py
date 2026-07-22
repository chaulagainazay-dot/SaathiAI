"""M15 Universal Connector Platform — unit + security tests (deterministic)."""
import hashlib
import hmac
import tempfile
import time

import pytest

from saathi.connectors.platform import registry as R
from saathi.connectors.platform import store as S
from saathi.connectors.platform import catalog, credentials, health, webhook, mcp
from saathi.connectors.platform.adapters import DeterministicAdapter, is_retryable, FailureClass
from saathi.connectors.platform.execution import ExecutionEngine, ExecRequest
from saathi.connectors.platform.models import (
    RiskClass, ToolDef, MutationClass, is_executable, ConnState, normalized_input_hash,
    APPROVAL_THRESHOLD,
)
from saathi.connectors.platform.sync import SyncRunner


@pytest.fixture
def eng():
    st = S.ConnectorStore(tempfile.mktemp(suffix=".db"))
    return ExecutionEngine(store=st), st


def test_risk_floor_not_downgradable():
    t = ToolDef(tool_id="x.send", connector_id="x", capability_id="send_email",
                name="s", risk_class=RiskClass.EXTERNAL_SIDE_EFFECT,
                requires_approval=False)
    assert t.requires_approval is True  # forced up by __post_init__


def test_capability_catalog():
    assert catalog.capability_risk("send_email") == RiskClass.EXTERNAL_SIDE_EFFECT
    assert catalog.capability_risk("read_local_file") == RiskClass.LOCAL_READ
    assert catalog.capability_risk("deploy_to_production") == RiskClass.HIGH_IMPACT


def test_registry_seeded():
    h = R.registry_health()
    assert h["connectors"] >= 10 and h["tools"] >= 20
    # honesty labels present
    assert "environment-blocked" in h["by_integration_status"]


def test_credentials_metadata_only():
    ref = credentials.new_ref(connector_id="gmail", scope="user:ajay",
                              backend="env", backend_key="NOPE_MISSING")
    d = ref.to_dict()
    assert "backend_key" in d and "NOPE" in d["backend_key"]
    # no secret value fields
    assert not any("secret" in k.lower() and k != "backend" for k in d)
    with pytest.raises(credentials.SecretUnavailable):
        credentials.resolve_secret(ref)


def test_lifecycle_gate():
    assert is_executable(ConnState.HEALTHY)
    assert is_executable(ConnState.CONNECTED)
    assert not is_executable(ConnState.EXPIRED)
    assert not is_executable(ConnState.UNAUTHORIZED)


def test_gateway_governed(eng):
    e, st = eng
    r = e.execute(ExecRequest(owner="a", tool_id="local_git.inspect_repository"))
    assert r.status == "success"
    assert "gateway_ref" in r.provenance  # proof it went through governance


def test_approval_binding(eng):
    e, st = eng
    aid = st.add_account(owner="a", connector_id="github", label="g", state="healthy")
    req = ExecRequest(owner="a", tool_id="github.create_issue", account_id=aid,
                      args={"title": "t"})
    assert e.execute(req).status == "approval_required"
    appr = e.request_approval(req)
    st.resolve_approval(appr["approval_id"], approved=True, actor="a")
    req.approval_id = appr["approval_id"]
    assert e.execute(req).status == "success"
    # single-use: reused approval no longer valid
    assert e.execute(req).status == "approval_required"
    # an approval for different args must NOT authorize this action
    req2 = ExecRequest(owner="a", tool_id="github.create_issue", account_id=aid,
                       args={"title": "DIFFERENT"}, approval_id=appr["approval_id"])
    assert e.execute(req2).status == "approval_required"


def test_idempotency_replay(eng):
    e, st = eng
    aid = st.add_account(owner="a", connector_id="github", label="g", state="healthy")
    k = "kk"
    a = e.execute(ExecRequest(owner="a", tool_id="github.list_issues", account_id=aid,
                              args={"_fixture": "success"}, idempotency_key=k))
    b = e.execute(ExecRequest(owner="a", tool_id="github.list_issues", account_id=aid,
                              args={"_fixture": "success"}, idempotency_key=k))
    assert a.status == "success" and b.provenance.get("replayed") is True


def test_uncertain_not_retryable(eng):
    e, st = eng
    aid = st.add_account(owner="a", connector_id="github", label="g", state="healthy")
    r = e.execute(ExecRequest(owner="a", tool_id="github.list_issues", account_id=aid,
                              args={"_fixture": "uncertain"}))
    assert r.status == "uncertain" and r.retryable is False
    assert not is_retryable(FailureClass.UNCERTAIN)
    assert not is_retryable(FailureClass.TIMEOUT, idempotent=False)  # non-idempotent path


def test_deterministic_fixtures():
    a = DeterministicAdapter()
    t = R.get_tool("github.list_issues")
    for fx, expect in [("success", "success"), ("auth_fail", "failed"),
                       ("rate_limit", "failed"), ("uncertain", "uncertain"),
                       ("partial", "partial")]:
        res = a.execute(tool=t, account_id="x", args={"_fixture": fx})
        assert res.status == expect


def test_health_honest():
    gh = health.connector_health("gmail")
    assert gh["status"] == "environment-blocked"  # no creds → not "healthy"
    lg = health.connector_health("local_git")
    assert lg["status"] == "healthy"


def test_webhook_security():
    st = S.ConnectorStore(tempfile.mktemp(suffix=".db"))
    sec, body = "s", b"{}"
    sig = "sha256=" + hmac.new(sec.encode(), body, hashlib.sha256).hexdigest()
    ok = webhook.receive(connector_id="github", raw_body=body, signature=sig,
                         event_ts=time.time(), dedup_key="e1", secret=sec, store=st)
    replay = webhook.receive(connector_id="github", raw_body=body, signature=sig,
                             event_ts=time.time(), dedup_key="e1", secret=sec, store=st)
    bad = webhook.receive(connector_id="github", raw_body=body, signature="sha256=x",
                          event_ts=time.time(), dedup_key="e2", secret=sec, store=st)
    stale = webhook.receive(connector_id="github", raw_body=body, signature=sig,
                            event_ts=time.time() - 9999, dedup_key="e3", secret=sec, store=st)
    assert ok["accepted"] and replay["reason"] == "replay"
    assert bad["reason"] == "bad_signature" and stale["reason"] == "stale"


def test_sync_resumable(eng):
    e, st = eng
    aid = st.add_account(owner="a", connector_id="github", label="g", state="healthy")
    sr = SyncRunner(engine=e, store=st)
    sid = sr.start(owner="a", connector_id="github")
    pages = iter([(["a", "b"], "t1"), (["c"], None)])
    res = sr.run(sync_id=sid, tool_id="github.list_issues", account_id=aid,
                 page_extractor=lambda d: next(pages), max_pages=10)
    assert res["stopped"] == "complete" and res["processed"] == 3


def test_mcp_untrusted_clamp():
    mcp.register_mcp_server(server_id="qa", display_name="QA",
                            tools=[{"name": "wipe", "read_only": False, "risk": "low"}])
    t = R.get_tool("mcp_qa.mcp_wipe")
    # server said "low" but we clamp UP to the side-effect floor + approval
    assert int(t.risk_class) >= int(APPROVAL_THRESHOLD) and t.requires_approval


def test_secret_redaction(eng):
    e, _ = eng
    red = e._redact("failed with token=abc123secret and cookie=xyz")
    assert "abc123secret" not in red and "[redacted]" in red
