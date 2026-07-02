"""Safety Harness tests (SES-002) — deterministic L0–L5 gating, AP-12.

Covers: rule-based classification (most-restrictive-wins), approval mapping,
capability-aware consistency validation (tool/model must match policy), and the
full gate enforcing that required approvals are present. No LLM, no network.
"""
import pytest

from saathi.safety import (
    SafetyHarness, SafetyLevel, Approval, ActionRequest, CapabilityPolicy,
    classify, default_approval, default_policies,
)


# ── deterministic classification ─────────────────────────────────────────
def test_classification_levels():
    assert classify("read_file") == SafetyLevel.L0
    assert classify("summarize_text") == SafetyLevel.L1
    assert classify("write_file") == SafetyLevel.L2
    assert classify("send_telegram") == SafetyLevel.L3
    assert classify("deploy_production") == SafetyLevel.L4
    assert classify("delete_database") == SafetyLevel.L5


def test_most_restrictive_wins():
    # contains both "read" (L0) and "delete" (L5) → L5
    assert classify("read_then_delete") == SafetyLevel.L5
    # "get" (L0) + "deploy" (L4) → L4
    assert classify("get_and_deploy") == SafetyLevel.L4


def test_unknown_tool_defaults_to_local_mod_not_free():
    assert classify("frobnicate_widget") == SafetyLevel.L2   # conservative, never L0


def test_approval_mapping():
    assert default_approval(SafetyLevel.L0) is Approval.AUTOMATIC
    assert default_approval(SafetyLevel.L3) is Approval.AUTOMATIC
    assert default_approval(SafetyLevel.L4) is Approval.HUMAN
    assert default_approval(SafetyLevel.L5) is Approval.CODE_CONFIRM


# ── capability-aware consistency ─────────────────────────────────────────
def test_deployment_policy_enforces_tool_and_model():
    h = SafetyHarness(default_policies())
    # correct tool + model → allowed (pending approval)
    d = h.evaluate(ActionRequest("deploy_production", capability="GitHub Deployment", model="openai/gpt-4o"))
    assert d.allowed is True
    assert d.level == SafetyLevel.L4
    assert d.approval is Approval.HUMAN
    assert d.audit is True

    # wrong tool for the capability → denied
    d2 = h.evaluate(ActionRequest("rm_everything", capability="GitHub Deployment", model="openai/gpt-4o"))
    assert d2.allowed is False
    assert any("not permitted" in r for r in d2.reasons)

    # disallowed model → denied
    d3 = h.evaluate(ActionRequest("deploy_production", capability="GitHub Deployment", model="groq/llama-3.3-70b"))
    assert d3.allowed is False
    assert any("model" in r for r in d3.reasons)


def test_policy_can_raise_level():
    h = SafetyHarness({
        "Risky": CapabilityPolicy("Risky", SafetyLevel.L4, Approval.HUMAN)
    })
    # tool alone classifies L0 (read), but policy raises to L4
    d = h.evaluate(ActionRequest("read_status", capability="Risky"))
    assert d.level == SafetyLevel.L4
    assert d.approval is Approval.HUMAN


def test_storyboard_policy_is_automatic():
    h = SafetyHarness(default_policies())
    d = h.evaluate(ActionRequest("storyboard_engine", capability="AI Studio Storyboard", model="ollama/local"))
    assert d.allowed is True
    assert d.approval is Approval.AUTOMATIC
    assert d.level == SafetyLevel.L1


# ── the full gate enforces approvals ─────────────────────────────────────
def test_gate_blocks_without_human_approval():
    h = SafetyHarness(default_policies())
    a = ActionRequest("deploy_production", capability="GitHub Deployment", model="openai/gpt-4o")
    blocked = h.gate(a)                              # no approval provided
    assert blocked.allowed is False
    assert any("human approval" in r for r in blocked.reasons)
    approved = h.gate(a, human_approved=True)        # approval provided
    assert approved.allowed is True


def test_gate_blocks_l5_without_code_confirmation():
    h = SafetyHarness()
    a = ActionRequest("delete_all_backups")
    assert h.gate(a).allowed is False                        # L5 needs code confirm
    assert h.gate(a, code_confirmed=True).allowed is True


def test_nothing_bypasses_read_only_is_automatic():
    h = SafetyHarness()
    d = h.gate(ActionRequest("list_files"))
    assert d.allowed is True
    assert d.level == SafetyLevel.L0
    assert d.approval is Approval.AUTOMATIC
