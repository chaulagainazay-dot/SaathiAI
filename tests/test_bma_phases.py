"""9-phase BMA loop tests (SES-002) — verifies the full Observe→…→UpdateMemory
sequence runs in order, and that the legacy 4-phase wrappers still delegate
to the nine phases. Complements test_bma.py (which covers behavior)."""
from unittest.mock import AsyncMock, patch

import pytest

from saathi.models import AgentState, Skill, StudentInput, ActionResult
from saathi.agents.master import MasterAgentLoop

NINE_PHASES = [
    "observe", "understand", "reason", "plan",
    "execute", "verify", "evaluate", "learn", "update_memory",
]


@pytest.mark.asyncio
async def test_all_nine_phases_run_in_order():
    master = MasterAgentLoop()
    seen: list[str] = []

    # Wrap each phase method to record invocation order, preserving behavior.
    for name in NINE_PHASES:
        orig = getattr(master, name)

        def make(n, fn):
            async def wrapper(*a, **k):
                seen.append(n)
                return await fn(*a, **k)
            return wrapper

        setattr(master, name, make(name, orig))

    mock_result = ActionResult(
        student_id="s1", skill="writing", response="Nice work!",
        corrections=[], band_estimate=6.0,
    )
    with patch.object(master.sub_agents[Skill.WRITING], "execute", new=AsyncMock(return_value=mock_result)), \
         patch.object(master.sub_agents[Skill.GRAMMAR], "execute", new=AsyncMock(return_value=mock_result)), \
         patch.object(master.sub_agents[Skill.VOCABULARY], "execute", new=AsyncMock(return_value=mock_result)):
        inp = StudentInput(student_id="s1", text="He go to school.", skill=Skill.WRITING)
        result = await master.run_loop(inp)

    assert seen == NINE_PHASES          # exact order, all nine
    assert master.state == AgentState.IDLE
    assert master.phase == "idle"
    assert result.band_estimate == 6.0


@pytest.mark.asyncio
async def test_legacy_wrappers_delegate_to_phases():
    """perceive/decide/act still work and produce the same types."""
    master = MasterAgentLoop()
    inp = StudentInput(student_id="s2", text="I spoke about my hometown.", skill=Skill.SPEAKING)
    perception = await master.perceive(inp)          # = observe + understand
    assert perception.detected_skill == Skill.SPEAKING
    decision = await master.decide(perception)        # = reason + plan
    assert decision.strategy.primary_skill == Skill.SPEAKING
