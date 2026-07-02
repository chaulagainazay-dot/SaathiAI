"""Agent Registry tests (SES-002 Part 4) — every agent declares a contract, AP-12."""
from saathi.agent_registry import (
    AgentRegistry, AgentContract, default_registry,
)
from saathi.model_router import ModelLabel
from saathi.safety import SafetyLevel, Approval


def test_default_registry_has_contracts_for_the_seven_subagents():
    r = default_registry()
    ids = {c.agent_id for c in r.all()}
    for skill in ("writing", "speaking", "reading", "listening",
                  "grammar", "vocabulary", "pronunciation"):
        assert f"{skill}_subagent" in ids
    # all tutoring agents share the department + are L1 (feedback only)
    assert all(c.department == "IELTS Tutor" for c in r.all())
    assert all(c.max_safety == SafetyLevel.L1 for c in r.all())


def test_contract_summary_is_serializable():
    r = default_registry()
    s = r.get("writing_subagent").summary()
    assert s["model_label"] == "standard"
    assert s["max_safety"] == "L1"
    assert s["approval"] == "automatic"


def test_uncontracted_flags_missing_contracts():
    r = default_registry()
    # a runtime agent with no contract is an SES-002 violation the registry surfaces
    missing = r.uncontracted(["writing_subagent", "rogue_agent"])
    assert missing == ["rogue_agent"]


def test_by_department_and_instance_registration():
    r = AgentRegistry()
    c = AgentContract("x_agent", "Studio", "does x", ModelLabel.REASONING,
                      SafetyLevel.L3, "read-all/write-self", approval=Approval.HUMAN)
    sentinel = object()
    r.register(c, instance=sentinel)
    assert r.by_department("Studio") == [c]
    assert r.instance("x_agent") is sentinel


def test_master_loop_registers_subagent_instances():
    """Reconciliation: the runtime's actual sub-agents become contract-backed."""
    from saathi.agents.master import MasterAgentLoop
    from saathi.agent_registry import registry
    MasterAgentLoop()   # its __init__ registers instances against contracts
    assert registry.instance("writing_subagent") is not None
