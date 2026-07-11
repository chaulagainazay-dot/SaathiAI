"""M17 Universal Computer Agent — perception, gateway-routed ops, verification,
replay, security."""
import tempfile

import pytest

from saathi.connectors.platform import store as S, registry as R
from saathi.connectors.platform.execution import ExecutionEngine
from saathi.computer_agent import ComputerAgent, provider_availability, Screen
from saathi.computer_agent.perception import ElementType, UIElement, BBox
from saathi.computer_agent.providers import default_provider
from saathi.computer_agent.replay import Replay


@pytest.fixture
def agent():
    eng = ExecutionEngine(store=S.ConnectorStore(tempfile.mktemp(suffix=".db")))
    return ComputerAgent(owner="ajay", engine=eng)


# ── perception ──────────────────────────────────────────────────────────────
def test_perceive_returns_canonical_screen():
    scr = default_provider("desktop").perceive(fixture="login")
    assert isinstance(scr, Screen) and len(scr.elements) >= 4
    submit = scr.find(semantic="submit login")
    assert submit and submit[0].type == ElementType.BUTTON and submit[0].clickable


def test_uielement_bbox_center():
    e = UIElement("x", ElementType.BUTTON, BBox(10, 20, 100, 40))
    assert e.bbox.center() == (60, 40)


# ── operations registered as connectors (gateway-routed) ────────────────────
def test_ops_registered_as_connectors():
    for cid in ("vision", "desktop", "browser_agent"):
        assert R.get_connector(cid) is not None
    assert R.get_tool("vision.capture_screen").risk_class == 0   # read
    assert int(R.get_tool("desktop.delete_item").risk_class) == 4  # manual-only


def test_read_op_no_approval(agent):
    r = agent.step(tool_id="vision.capture_screen", args={"_fixture": "login"}, actor_type="user")
    assert r["status"] == "success" and r["data"]["element_count"] >= 4
    assert "gateway_ref" in r["provenance"]   # gateway-routed, no bypass


def test_click_verifies(agent):
    r = agent.step(tool_id="desktop.click",
                   args={"target": "el_submit", "_expect_text": "Sign in"}, actor_type="user")
    assert r["status"] == "success" and r["data"]["verification"]["verified"] is True


def test_unverified_action_is_uncertain(agent):
    r = agent.step(tool_id="desktop.click", args={"target": "x", "_expect": "error"},
                   actor_type="user")
    assert r["status"] == "uncertain"          # never assume success


# ── approvals: destructive / side-effect gated ──────────────────────────────
def test_delete_requires_approval_or_blocked(agent):
    r = agent.step(tool_id="desktop.delete_item", args={"target": "f"}, actor_type="user")
    assert r["status"] in ("approval_required", "blocked")


def test_send_and_purchase_gated(agent):
    assert agent.step(tool_id="browser_agent.send_message", args={"text": "hi"},
                      actor_type="user")["status"] == "approval_required"
    d = agent.describe(tool_id="browser_agent.submit_purchase", args={"item": "x"})
    assert d["risk_class"] == 4 and d["manual_only"] is True


# ── replay: sanitized, no secrets ───────────────────────────────────────────
def test_replay_redacts_credentials():
    rp = Replay(workflow_id="w", owner="ajay")
    rp.record(tool_id="desktop.type_text",
              args={"password": "hunter2", "otp": "999", "target": "el"},
              status="success", verified=True)
    blob = str(rp.to_dict())
    assert "hunter2" not in blob and "999" not in blob and "[REDACTED]" in blob


def test_agent_replay_timeline(agent):
    agent.step(tool_id="vision.capture_screen", args={"_fixture": "login"}, actor_type="user")
    agent.step(tool_id="desktop.click", args={"target": "el_submit", "_expect_text": "Sign in"},
               actor_type="user")
    tl = agent.timeline()
    assert len(tl) == 2 and "vision.capture_screen" in tl[0] and "✓" in tl[1]


# ── providers: honest availability (no live desktop faked) ──────────────────
def test_provider_availability_honest():
    pa = provider_availability()
    assert pa["vision_llm"]["status"] == "environment_blocked"
    assert pa["deterministic"]["available"] is True
    # each backend reports available/environment_blocked, never a fake "healthy"
    for k, v in pa.items():
        assert v["status"] in ("available", "environment_blocked", "deterministic")


# ── security: cross-user desktop history isolation ──────────────────────────
def test_cross_user_desktop_history_isolated(agent):
    agent.step(tool_id="vision.capture_screen", args={"_fixture": "login"}, actor_type="user")
    attacker = agent.engine.store.list_executions("attacker")
    assert attacker == []
