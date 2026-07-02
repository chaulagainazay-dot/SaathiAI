"""MasterAgentLoop — the 9-phase BMA cognitive loop (SES-002).

Phases:  Observe → Understand → Reason → Plan → Execute → Verify →
         Evaluate → Learn → Update Memory

The four legacy grouping methods (perceive / decide / act / reflect) are kept
as thin wrappers over the nine phases so existing callers and tests are
unaffected:
    perceive = observe + understand
    decide   = reason  + plan
    act      = execute + verify
    reflect  = evaluate + learn + update_memory
"""
from __future__ import annotations
import os
from typing import Any

from groq import AsyncGroq

from ..memory import HierarchicalMemory
from ..models import (
    AgentState, Skill, StudentInput, Perception, Strategy, Decision, ActionResult
)
from .harness import SafetyHarness
from .bus import AgentMessageBus
from .sub_agents import (
    WritingSubAgent, SpeakingSubAgent, ReadingSubAgent, ListeningSubAgent,
    GrammarSubAgent, VocabularySubAgent, PronunciationSubAgent,
)

_GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

_groq_client: AsyncGroq | None = None


def _get_groq() -> AsyncGroq:
    global _groq_client
    if _groq_client is None:
        _groq_client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
    return _groq_client


# Keyword-based skill detection (fast fallback before LLM)
_SKILL_KEYWORDS: dict[Skill, list[str]] = {
    Skill.WRITING: ["essay", "task 1", "task 2", "write", "writing", "paragraph"],
    Skill.SPEAKING: ["said", "spoke", "speaking", "part 1", "part 2", "part 3", "transcript"],
    Skill.READING: ["passage", "reading", "true", "false", "not given", "tnfg", "yng"],
    Skill.LISTENING: ["heard", "listening", "audio", "form", "note"],
    Skill.GRAMMAR: ["grammar", "tense", "article", "preposition", "sentence"],
    Skill.VOCABULARY: ["word", "vocab", "synonym", "phrase", "collocation"],
}


def _detect_skill_heuristic(text: str) -> Skill:
    lower = text.lower()
    scores: dict[Skill, int] = {s: 0 for s in Skill}
    for skill, keywords in _SKILL_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                scores[skill] += 1
    best = max(scores, key=lambda s: scores[s])
    return best if scores[best] > 0 else Skill.WRITING  # default


class MasterAgentLoop:
    def __init__(self):
        self.state = AgentState.IDLE
        self.memory = HierarchicalMemory()
        self.harness = SafetyHarness()
        self.bus = AgentMessageBus()
        self.sub_agents: dict[Skill, Any] = {
            Skill.WRITING: WritingSubAgent(),
            Skill.SPEAKING: SpeakingSubAgent(),
            Skill.READING: ReadingSubAgent(),
            Skill.LISTENING: ListeningSubAgent(),
            Skill.GRAMMAR: GrammarSubAgent(),
            Skill.VOCABULARY: VocabularySubAgent(),
            Skill.PRONUNCIATION: PronunciationSubAgent(),
        }
        # SES-002 Part 4: every runtime agent must be contract-backed. Register
        # each sub-agent's instance against its declared contract in the Agent
        # Registry (contracts are declared in saathi/agent_registry.py).
        try:
            from ..agent_registry import registry as agent_registry
            for skill, inst in self.sub_agents.items():
                contract = agent_registry.get(f"{skill.value}_subagent")
                if contract is not None:
                    agent_registry.register(contract, instance=inst)
        except Exception:
            pass  # registry wiring must never block the runtime
        # Subscribe master to cross-skill escalations
        self.bus.subscribe(self._handle_cross_pattern)
        self.phase = "idle"   # fine-grained 9-phase tracker (observability)

    # ── Public entry point ────────────────────────────────────────────────────

    async def run_loop(self, student_input: StudentInput) -> ActionResult:
        self.state = AgentState.PERCEIVING
        # PHASE 1: OBSERVE — gather raw facts (skill, context), no interpretation
        observation = await self.observe(student_input)
        # PHASE 2: UNDERSTAND — interpret intent, form the Perception
        perception = await self.understand(observation)

        self.state = AgentState.DECIDING
        # PHASE 3: REASON — analyse cross-skill patterns, choose an approach
        reasoning = await self.reason(perception)
        # PHASE 4: PLAN — commit to a strategy/decision
        decision = await self.plan(perception, reasoning)

        self.state = AgentState.ACTING
        # PHASE 5: EXECUTE — run sub-agents (safety-gated by harness.monitor)
        raw_result = await self.execute(decision, perception)
        # PHASE 6: VERIFY — validate output, publish to the domain bus
        result = await self.verify(raw_result, perception)

        self.state = AgentState.REFLECTING
        # PHASE 7: EVALUATE — assess quality, surface recurring patterns
        evaluation = await self.evaluate(result, perception)
        # PHASE 8: LEARN — derive lessons from this interaction
        await self.learn(evaluation, result)
        # PHASE 9: UPDATE MEMORY — persist the interaction
        await self.update_memory(result, perception)

        self.state = AgentState.IDLE
        self.phase = "idle"
        return result

    # ── The nine phases ─────────────────────────────────────────────────────────

    async def observe(self, student_input: StudentInput) -> dict:
        self.phase = "observe"
        detected_skill = student_input.skill or _detect_skill_heuristic(student_input.text)
        context = self.memory.get_context(student_input.student_id)
        return {
            "student_input": student_input,
            "detected_skill": detected_skill,
            "context": {**context, **student_input.metadata},
        }

    async def understand(self, observation: dict) -> Perception:
        self.phase = "understand"
        si: StudentInput = observation["student_input"]
        detected_skill: Skill = observation["detected_skill"]
        intent = await self._classify_intent(si.text, detected_skill)
        return Perception(
            student_id=si.student_id,
            raw_input=si.text,
            detected_skill=detected_skill,
            intent=intent,
            confidence=0.85,
            context=observation["context"],
        )

    async def reason(self, perception: Perception) -> dict:
        self.phase = "reason"
        cross_patterns = self.bus.get_cross_patterns(perception.student_id)
        approach = self._pick_approach(perception.intent, cross_patterns)
        extra_agents: list[Skill] = []
        if perception.detected_skill in (Skill.WRITING, Skill.SPEAKING):
            extra_agents = [Skill.GRAMMAR, Skill.VOCABULARY]
        return {"approach": approach, "cross_patterns": cross_patterns, "extra_agents": extra_agents}

    async def plan(self, perception: Perception, reasoning: dict) -> Decision:
        self.phase = "plan"
        strategy = Strategy(
            primary_skill=perception.detected_skill,
            approach=reasoning["approach"],
            sub_agents_to_invoke=reasoning["extra_agents"],
            parameters={},
        )
        return Decision(
            strategy=strategy,
            rationale=f"Skill={perception.detected_skill.value}, intent={perception.intent}",
            cross_skill_patterns=[p["error_type"] for p in reasoning["cross_patterns"]],
        )

    async def execute(self, decision: Decision, perception: Perception) -> ActionResult:
        self.phase = "execute"
        async with self.harness.monitor(perception):
            primary = self.sub_agents[decision.strategy.primary_skill]
            result = await primary.execute(perception, decision.strategy, perception.context)
            # Run micro-agents and merge corrections
            for skill in decision.strategy.sub_agents_to_invoke:
                micro = self.sub_agents.get(skill)
                if micro:
                    micro_result = await micro.execute(
                        perception, decision.strategy, perception.context
                    )
                    result.corrections.extend(micro_result.corrections)
            return result

    async def verify(self, result: ActionResult, perception: Perception) -> ActionResult:
        self.phase = "verify"
        result = await self.harness.validate_output(result)
        await self.bus.publish(result)
        return result

    async def evaluate(self, result: ActionResult, perception: Perception) -> dict:
        self.phase = "evaluate"
        patterns = self.bus.get_cross_patterns(perception.student_id)
        if patterns:
            result.reflection_notes = [
                f"⚠ Recurring {p['error_type']} error across: {', '.join(p['skills'])}"
                for p in patterns
            ]
        return {"patterns": patterns}

    async def learn(self, evaluation: dict, result: ActionResult) -> None:
        self.phase = "learn"
        # Cross-skill patterns are learned into working memory by the bus
        # (via _handle_cross_pattern on publish). Here we record, on the
        # result, what was learned this cycle — observable and non-duplicating.
        if evaluation.get("patterns"):
            result.metadata["learned_patterns"] = [p["error_type"] for p in evaluation["patterns"]]

    async def update_memory(self, result: ActionResult, perception: Perception) -> None:
        self.phase = "update_memory"
        interaction = {
            "skill": result.skill,
            "input_text": perception.raw_input,
            "response": result.response,
            "feedback": result.feedback,
            "band_est": result.band_estimate,
            "corrections": result.corrections,
            "metadata": result.metadata,
        }
        await self.memory.store_interaction(perception.student_id, interaction)

    # ── Legacy grouping wrappers (preserve the 4-phase public API) ──────────────

    async def perceive(self, student_input: StudentInput) -> Perception:
        return await self.understand(await self.observe(student_input))

    async def decide(self, perception: Perception) -> Decision:
        return await self.plan(perception, await self.reason(perception))

    async def act(self, decision: Decision, perception: Perception) -> ActionResult:
        return await self.verify(await self.execute(decision, perception), perception)

    async def reflect(self, result: ActionResult, perception: Perception) -> None:
        evaluation = await self.evaluate(result, perception)
        await self.learn(evaluation, result)
        await self.update_memory(result, perception)

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _classify_intent(self, text: str, skill: Skill) -> str:
        lower = text.lower()
        if "?" in text:
            return "question"
        if any(w in lower for w in ["check", "correct", "fix", "review"]):
            return "correction_request"
        return "practice"

    def _pick_approach(self, intent: str, cross_patterns: list) -> str:
        if cross_patterns:
            return "intervention"  # recurring cross-skill error
        if intent == "question":
            return "socratic"
        if intent == "correction_request":
            return "direct_correction"
        return "encouragement"

    async def _handle_cross_pattern(
        self, student_id: str, error_type: str, skills: list[str]
    ) -> None:
        """Called by the bus when the same error type appears across ≥2 skills."""
        note = (
            f"Cross-skill pattern detected for {student_id}: "
            f"'{error_type}' in {skills}. Scheduling intervention."
        )
        # Store as a high-priority item in working memory
        self.memory.working.add(student_id, {"type": "intervention", "error": error_type, "skills": skills})


# Module-level singleton (lazy, avoids import-time side effects)
_master: MasterAgentLoop | None = None


def get_master() -> MasterAgentLoop:
    global _master
    if _master is None:
        _master = MasterAgentLoop()
    return _master
