"""Runtime Governance Engine tests — the layers beyond L0–L5 classification (AP-12).

Covers Identity (L3), Resource guardrails (L5, Storage-wired), profile-driven
Approval (L6), Audit (L7), Risk scoring (L9), and Safety Profiles. Deterministic,
injected dependencies, no network.
"""
from saathi.safety import (
    SafetyHarness, SafetyLevel, Approval, Identity, SafetyProfile,
    ActionRequest, CapabilityPolicy, approval_for, risk_score,
)


# ── L3 Identity ──────────────────────────────────────────────────────────
def test_identity_must_be_permitted():
    h = SafetyHarness({
        "Admin Only": CapabilityPolicy("Admin Only", SafetyLevel.L4, Approval.HUMAN,
                                       allowed_identities=frozenset({Identity.ADMIN}))
    })
    ok = h.evaluate(ActionRequest("deploy", capability="Admin Only", identity=Identity.ADMIN))
    assert ok.identity_ok is True
    bad = h.evaluate(ActionRequest("deploy", capability="Admin Only", identity=Identity.GUEST))
    assert bad.allowed is False and bad.identity_ok is False


def test_scheduled_job_identity_allowed_for_automation_capability():
    h = SafetyHarness({
        "Scheduled Cleanup": CapabilityPolicy("Scheduled Cleanup", SafetyLevel.L2, Approval.AUTOMATIC,
                             allowed_identities=frozenset({Identity.AUTOMATION, Identity.SCHEDULED_JOB}))
    })
    d = h.evaluate(ActionRequest("cleanup_temp", capability="Scheduled Cleanup",
                                 identity=Identity.SCHEDULED_JOB))
    assert d.allowed is True


# ── L5 Resource guardrails (Storage Intelligence integration) ────────────
def test_resource_guardrail_blocks_when_insufficient():
    def not_enough_disk(action):
        return False, "needs 38GB, only 20GB free"
    h = SafetyHarness(resource_check=not_enough_disk)
    d = h.gate(ActionRequest("render_video"))
    assert d.allowed is False
    assert d.resource_ok is False
    assert any("38GB" in r for r in d.reasons)


# ── L6 Approval by profile ───────────────────────────────────────────────
def test_profile_changes_approval_for_same_action():
    # L3 external action: auto in development, human in production.
    assert approval_for(SafetyLevel.L3, SafetyProfile.DEVELOPMENT) is Approval.AUTOMATIC
    assert approval_for(SafetyLevel.L3, SafetyProfile.PRODUCTION) is Approval.HUMAN

    dev = SafetyHarness(profile=SafetyProfile.DEVELOPMENT)
    prod = SafetyHarness(profile=SafetyProfile.PRODUCTION)
    a = ActionRequest("send_email")
    assert dev.evaluate(a).approval is Approval.AUTOMATIC
    assert prod.evaluate(a).approval is Approval.HUMAN


def test_offline_profile_denies_external_actions():
    h = SafetyHarness(profile=SafetyProfile.OFFLINE)
    d = h.evaluate(ActionRequest("publish_post"))   # L3 external
    assert d.allowed is False
    assert any("OFFLINE" in r for r in d.reasons)
    # but local read still fine
    assert h.evaluate(ActionRequest("read_file")).allowed is True


def test_emergency_profile_is_most_restrictive():
    h = SafetyHarness(profile=SafetyProfile.EMERGENCY)
    d = h.evaluate(ActionRequest("write_file"))   # L2
    assert d.approval is Approval.HUMAN            # L2 needs human in emergency


# ── L9 Risk scoring ──────────────────────────────────────────────────────
def test_risk_scales_with_level():
    r0, c0 = risk_score(SafetyLevel.L0, matched=True)
    r5, c5 = risk_score(SafetyLevel.L5, matched=True)
    assert r0 == 0.0 and r5 == 1.0
    assert c0 == 0.97
    # unmatched (defaulted) classification → lower confidence
    _, c_unmatched = risk_score(SafetyLevel.L2, matched=False)
    assert c_unmatched < c0


def test_decision_carries_risk_and_confidence():
    h = SafetyHarness()
    d = h.evaluate(ActionRequest("deploy_production"))
    assert d.level == SafetyLevel.L4
    assert d.risk == 0.8
    assert d.confidence == 0.97


# ── L7 Audit ─────────────────────────────────────────────────────────────
def test_gate_always_audits():
    records = []
    h = SafetyHarness(audit_sink=records.append)
    h.gate(ActionRequest("delete_database", identity=Identity.ADMIN, why="cleanup old data"))
    assert len(records) == 1
    rec = records[0]
    assert rec["who"] == "admin"
    assert rec["what"] == "delete_database"
    assert rec["why"] == "cleanup old data"
    assert rec["level"] == "L5"
    assert rec["result"] == "denied"      # L5 needs code confirmation
    assert "risk" in rec and "when" in rec


# ── L5 ↔ Storage Intelligence integration ────────────────────────────────
def test_governance_blocks_render_that_cant_finish_on_disk():
    from saathi.safety import storage_resource_check
    from saathi.storage import PredictiveStorageEngine, RenderPlan

    plan = RenderPlan(scene_count=60, avg_scene_duration_s=4.0, fps=24,
                      width=1080, height=1920, renderer="comfyui")
    # Only 2 GB free — a big ComfyUI render cannot finish.
    predictive = PredictiveStorageEngine(free_reader=lambda: 2_000_000_000)
    check = storage_resource_check(predictive, plan_for=lambda a: plan if a.tool == "render_video" else None)

    h = SafetyHarness(resource_check=check)
    denied = h.gate(ActionRequest("render_video"))
    assert denied.allowed is False and denied.resource_ok is False
    assert any("free" in r for r in denied.reasons)

    # A non-render action passes the storage guardrail untouched.
    assert h.evaluate(ActionRequest("read_file")).resource_ok is True
