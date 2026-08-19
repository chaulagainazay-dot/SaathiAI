"""R2.1-S1/S2 — the authority boundary.

These tests encode one invariant: no identity signal may create authority.

Not a voiceprint, not a face, not a device, not a channel, not a model's
opinion, not a boolean in a request body. An identity signal may be carried as
bounded metadata (``speaker_match_observed``) and nothing more.

Before this repair, ``{"text": "...", "speaker_verified": true}`` posted to
``/api/v1/agent/chat`` selected ``Identity.ADMIN``, bypassed the privileged-tool
gate, and satisfied both ``human_approved`` and ``code_confirmed`` — forging
ApprovalCenter approval. Each test below pins one part of that path shut.

The endpoint contracts that carried the forged field are covered separately in
``test_r2_1_endpoint_auth``; this file is about the authority itself.
"""
import inspect

import pytest

from saathi import server
from saathi.tools import registry
from saathi.tools.registry import execute_tool, recent_governance_decisions


@pytest.fixture(autouse=True)
def _reset_governance():
    registry._governance_harness = None
    registry._governance_audit.clear()
    yield


# ── S1: the shared contract of the advisory turn ──────────────────────────


def test_safe_respond_takes_no_authority_argument():
    params = inspect.signature(server._safe_respond).parameters
    assert "speaker_verified" not in params
    assert params["speaker_match_observed"].default is None


# ── S1: the shared authority boundary ─────────────────────────────────────


def test_execute_tool_rejects_the_forged_authority_kwarg():
    with pytest.raises(TypeError):
        execute_tool("system_health", {}, speaker_verified=True)


@pytest.mark.parametrize("observed", [True, False, None])
def test_speaker_match_never_selects_admin(observed):
    registry._HANDLERS["r2_1_probe_read"] = lambda **kw: {"ok": True}
    try:
        execute_tool("r2_1_probe_read", {}, speaker_match_observed=observed)
        audit = recent_governance_decisions()
        assert audit, "dispatch was not audited"
        assert audit[0]["who"] == "user"
        assert audit[0]["who"] != "admin"
    finally:
        del registry._HANDLERS["r2_1_probe_read"]


@pytest.mark.parametrize("observed", [True, False, None])
def test_speaker_match_never_satisfies_approval(observed):
    """An L5 action needs CODE_CONFIRM; no observation may supply it."""
    ran = {"n": 0}
    registry._HANDLERS["delete_all_records_r2_1"] = (
        lambda **kw: ran.__setitem__("n", ran["n"] + 1) or {"ok": True})
    try:
        out = execute_tool("delete_all_records_r2_1", {},
                           speaker_match_observed=observed)
        assert out["error"] == "governance_denied"
        assert out["level"] == "L5"
        assert ran["n"] == 0
    finally:
        del registry._HANDLERS["delete_all_records_r2_1"]


def test_governance_gate_is_never_handed_an_approval_by_the_legacy_path():
    """Source-level pin: the boolean-forgery wiring must not come back."""
    source = inspect.getsource(execute_tool)
    assert "human_approved=False" in source
    assert "code_confirmed=False" in source
    assert "Identity.USER" in source
    assert "Identity.ADMIN" not in source
    assert "human_approved=speaker" not in source
    assert "code_confirmed=speaker" not in source


def test_no_production_module_passes_speaker_verified():
    """Nothing in the shipped tree may reintroduce the parameter."""
    import pathlib
    root = pathlib.Path(server.__file__).resolve().parent
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for num, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or "``" in line:
                continue
            if "speaker_verified=" in line:
                offenders.append(f"{path.relative_to(root)}:{num}")
    assert not offenders, f"speaker_verified still passed at: {offenders}"


def test_agent_prompt_does_not_claim_the_speaker_is_authenticated():
    """The model must not be told the speaker is the owner."""
    from saathi.agent import SaathiAgent
    source = inspect.getsource(SaathiAgent.respond)
    assert "Speaker verified as Ajay" not in source
    assert "speaker_match_observed" in source
    assert "grants no additional" in source
