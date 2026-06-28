"""MasterAgentLoop — Perception → Decision → Action → Reflection."""
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
        # Subscribe master to cross-skill escalations
        self.bus.subscribe(self._handle_cross_pattern)

    # ── Public entry point ────────────────────────────────────────────────────

    async def run_loop(self, student_input: StudentInput) -> ActionResult:
        self.state = AgentState.PERCEIVING

        # PHASE 1: PERCEPTION
        perception = await self.perceive(student_input)

        # PHASE 2: DECISION
        self.state = AgentState.DECIDING
        decision = await self.decide(perception)

        # PHASE 3: ACTION
        self.state = AgentState.ACTING
        action_result = await self.act(decision, perception)

        # PHASE 4: REFLECTION
        self.state = AgentState.REFLECTING
        await self.reflect(action_result, perception)

        self.state = AgentState.IDLE
        return action_result

    # ── Phases ────────────────────────────────────────────────────────────────

    async def perceive(self, student_input: StudentInput) -> Perception:
        detected_skill = student_input.skill or _detect_skill_heuristic(student_input.text)
        context = self.memory.get_context(student_input.student_id)

        # Use LLM to classify intent (socratic/correction/question)
        intent = await self._classify_intent(student_input.text, detected_skill)

        return Perception(
            student_id=student_input.student_id,
            raw_input=student_input.text,
            detected_skill=detected_skill,
            intent=intent,
            confidence=0.85,
            context={**context, **student_input.metadata},
        )

    async def decide(self, perception: Perception) -> Decision:
        cross_patterns = self.bus.get_cross_patterns(perception.student_id)
        approach = self._pick_approach(perception.intent, cross_patterns)

        # Invoke micro-agents for writing/speaking to enrich feedback
        extra_agents: list[Skill] = []
        if perception.detected_skill in (Skill.WRITING, Skill.SPEAKING):
            extra_agents = [Skill.GRAMMAR, Skill.VOCABULARY]

        strategy = Strategy(
            primary_skill=perception.detected_skill,
            approach=approach,
            sub_agents_to_invoke=extra_agents,
            parameters={},
        )
        return Decision(
            strategy=strategy,
            rationale=f"Skill={perception.detected_skill.value}, intent={perception.intent}",
            cross_skill_patterns=[p["error_type"] for p in cross_patterns],
        )

    async def act(self, decision: Decision, perception: Perception) -> ActionResult:
        async with self.harness.monitor(perception):
            primary = self.sub_agents[decision.strategy.primary_skill]
            result = await primary.execute(
                perception, decision.strategy, perception.context
            )

            # Run micro-agents and merge corrections
            for skill in decision.strategy.sub_agents_to_invoke:
                micro = self.sub_agents.get(skill)
                if micro:
                    micro_result = await micro.execute(
                        perception, decision.strategy, perception.context
                    )
                    result.corrections.extend(micro_result.corrections)

            result = await self.harness.validate_output(result)
            await self.bus.publish(result)
            return result

    async def reflect(self, result: ActionResult, perception: Perception) -> None:
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

        # Note cross-skill patterns in result for frontend display
        patterns = self.bus.get_cross_patterns(perception.student_id)
        if patterns:
            result.reflection_notes = [
                f"⚠ Recurring {p['error_type']} error across: {', '.join(p['skills'])}"
                for p in patterns
            ]

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
