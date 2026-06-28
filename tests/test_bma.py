"""Tests for Baadar Multi-Agent Architecture."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from saathi.models import AgentState, Skill, StudentInput, Perception, Strategy, ActionResult
from saathi.memory import WorkingMemory, HierarchicalMemory
from saathi.agents.harness import SafetyHarness, ContentFilter, PedagogyChecker
from saathi.agents.bus import AgentMessageBus
from saathi.agents.master import MasterAgentLoop


# ── Model tests ───────────────────────────────────────────────────────────────

def test_student_input_creation():
    inp = StudentInput(student_id="s1", text="My hometown is Kathmandu.")
    assert inp.student_id == "s1"
    assert inp.skill is None

def test_action_result_defaults():
    r = ActionResult(student_id="s1", skill="writing", response="Good essay.")
    assert r.safe is True
    assert r.corrections == []
    assert r.xp_delta == 0


# ── Working memory ────────────────────────────────────────────────────────────

def test_working_memory_add_and_get():
    wm = WorkingMemory()
    wm.add("s1", {"text": "hello"})
    wm.add("s1", {"text": "world"})
    assert len(wm.get("s1")) == 2

def test_working_memory_recent():
    wm = WorkingMemory()
    for i in range(10):
        wm.add("s1", {"i": i})
    recent = wm.recent("s1", n=3)
    assert len(recent) == 3
    assert recent[-1]["i"] == 9

def test_working_memory_max_capacity():
    wm = WorkingMemory()
    for i in range(25):
        wm.add("s1", {"i": i})
    items = wm.get("s1")
    assert len(items) == 20  # maxlen=20

def test_working_memory_clear():
    wm = WorkingMemory()
    wm.add("s1", {"x": 1})
    wm.clear("s1")
    assert wm.get("s1") == []


# ── Safety harness ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_content_filter_blocks_bad_input():
    perception = Perception(
        student_id="s1", raw_input="how to hack the exam",
        detected_skill=Skill.WRITING, intent="question", confidence=0.9
    )
    harness = SafetyHarness()
    with pytest.raises(ValueError, match="blocked"):
        await harness.validate_input(perception)

@pytest.mark.asyncio
async def test_content_filter_passes_good_input():
    perception = Perception(
        student_id="s1", raw_input="My essay is about climate change.",
        detected_skill=Skill.WRITING, intent="practice", confidence=0.9
    )
    harness = SafetyHarness()
    await harness.validate_input(perception)  # should not raise

@pytest.mark.asyncio
async def test_harness_clamps_band_estimate():
    harness = SafetyHarness()
    result = ActionResult(student_id="s1", skill="writing", response="ok", band_estimate=15.0)
    sanitised = await harness.validate_output(result)
    assert sanitised.band_estimate == 9.0

def test_pedagogy_checker_valid_band():
    pc = PedagogyChecker()
    result = ActionResult(student_id="s1", skill="writing", response="ok", band_estimate=6.5)
    ok, _ = pc.check_result(result)
    assert ok is True


# ── Agent message bus ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bus_no_escalation_single_skill():
    bus = AgentMessageBus()
    escalated = []
    bus.subscribe(lambda sid, et, skills: escalated.append((sid, et, skills)) or asyncio.sleep(0))

    result = ActionResult(
        student_id="s1", skill="writing", response="ok",
        corrections=[{"type": "grammar", "error": "He go", "suggestion": "He goes"}]
    )
    await bus.publish(result)
    assert escalated == []

@pytest.mark.asyncio
async def test_bus_escalates_cross_skill_pattern():
    bus = AgentMessageBus()
    escalated = []

    async def handler(sid, et, skills):
        escalated.append((sid, et, skills))

    bus.subscribe(handler)

    r1 = ActionResult(student_id="s1", skill="writing", response="ok",
                      corrections=[{"type": "grammar", "error": "x"}])
    r2 = ActionResult(student_id="s1", skill="speaking", response="ok",
                      corrections=[{"type": "grammar", "error": "y"}])
    await bus.publish(r1)
    await bus.publish(r2)
    assert len(escalated) == 1
    assert escalated[0][1] == "grammar"
    assert "writing" in escalated[0][2] and "speaking" in escalated[0][2]

def test_bus_get_cross_patterns():
    bus = AgentMessageBus()
    bus._patterns["s1"]["grammar"].add("writing")
    bus._patterns["s1"]["grammar"].add("speaking")
    patterns = bus.get_cross_patterns("s1")
    assert any(p["error_type"] == "grammar" for p in patterns)


# ── Master loop (mocked LLM) ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_master_loop_skill_detection():
    master = MasterAgentLoop()
    inp = StudentInput(student_id="s1", text="My essay discusses climate change.")
    perception = await master.perceive(inp)
    assert perception.detected_skill == Skill.WRITING

@pytest.mark.asyncio
async def test_master_loop_speaking_detection():
    master = MasterAgentLoop()
    inp = StudentInput(student_id="s2", text="I spoke about my hometown in part 1.")
    perception = await master.perceive(inp)
    assert perception.detected_skill == Skill.SPEAKING

@pytest.mark.asyncio
async def test_master_loop_full_cycle():
    master = MasterAgentLoop()

    # Mock sub-agent execute to avoid real Groq calls
    mock_result = ActionResult(
        student_id="s1", skill="writing", response="Good effort!",
        corrections=[{"type": "grammar", "error": "he go", "suggestion": "he goes"}],
        band_estimate=6.0, xp_delta=10
    )

    with patch.object(master.sub_agents[Skill.WRITING], "execute", new=AsyncMock(return_value=mock_result)), \
         patch.object(master.sub_agents[Skill.GRAMMAR], "execute", new=AsyncMock(return_value=mock_result)), \
         patch.object(master.sub_agents[Skill.VOCABULARY], "execute", new=AsyncMock(return_value=mock_result)):

        inp = StudentInput(student_id="s1", text="He go to school every day.", skill=Skill.WRITING)
        result = await master.run_loop(inp)

    assert result.student_id == "s1"
    assert result.band_estimate == 6.0
    assert master.state == AgentState.IDLE
