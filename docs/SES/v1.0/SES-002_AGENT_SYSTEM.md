```
================================================================================
SaathiAI Engineering Specification (SES)
================================================================================
Document Title      : Agent System
Document ID         : SES-002
Version             : 1.0.0
Status              : Approved
Maturity            : L3
Classification      : Internal
Owner               : SaathiAI Architecture Team
Primary Repository  : github.com/chaulagainazay/SaathiAI
Created             : 2026-07-02
Last Updated        : 2026-07-02
Next Review         : 2026-10-02
================================================================================
```

---

## Revision History

| Version | Date | Author | Summary of Changes |
|---------|------|--------|--------------------|
| 0.1.0 | 2026-07-02 | Ajay Chaulagain | Initial draft |
| 1.0.0 | 2026-07-02 | Ajay Chaulagain | Approved — 10-section complete agent system specification |

---

## Why This Document Exists

`SES-001_ARCHITECTURE.md` tells us where everything lives.

This document tells us how everything **thinks**.

The architecture defines the skeleton. The agent system defines the mind. Every other specification in this series — Knowledge Graph, Voice OS, AI Studio, Mission Control — describes a subsystem that either feeds into the agent system, is orchestrated by it, or depends on the contracts it defines.

If SES-001 is the map, SES-002 is the operating system for the organisms that live on it.

This document is authoritative on four things:

1. **What an agent is** — precise definitions that eliminate ambiguity across all future documents
2. **How agents think** — the BMA loop, phase by phase, with inputs, outputs, events, and failure handling
3. **How agents are governed** — contracts, capability matrices, safety classification, and approval requirements
4. **How agents grow** — from today's set to potentially hundreds without architectural change

All future agent implementations must conform to the contracts defined here. An agent that cannot pass the four-question subsystem test from SES-001, that violates the safety classification in Part 6, or that accesses memory beyond its policy in Part 7, is an architectural violation.

---

## Audience

| Role | Required Sections | Notes |
|------|------------------|-------|
| All Engineers | All | Every line of agent code is governed by this document |
| AI Coding Agents | All | The contracts in Parts 4 and 5 are your implementation specification |
| Product Architects | Parts 1–3, 10 | Understand the agent model before proposing product features |
| Ops / Mission Control | Parts 6, 9 | Safety classification and failure recovery |
| New Contributors | Read in full before writing any agent code | |

---

## Reading Order

```
SES-000C Architecture Principles  ← AP-01 through AP-10 constrain agent design
        │
        ▼
SES-001 Architecture               ← Folder structure, service registry, dependency rules
        │
        ▼
SES-002 Agent System               ← You are here
        │
        ▼
SES-003 Memory & Knowledge Graph   ← Memory access governed by Part 7 of this document
SES-004 Voice OS                   ← Uses agent contracts from Part 4
SES-005 AI Studio                  ← Studio Department governed by Part 3
```

---

## Document Structure

| Part | Title | The Question It Answers |
|------|-------|------------------------|
| 1 | Agent Philosophy | What is an agent? How does SaathiAI define the terms? |
| 2 | BMA Loop | How does an agent think? Phase by phase. |
| 3 | Department Hierarchy | How are agents organized? Who reports to whom? |
| 4 | Agent Contract | What must every agent declare? |
| 5 | Tool Registry | What must every tool declare? |
| 6 | SafetyHarness | What can agents do without asking first? |
| 7 | Memory Access Policy | What memory can each agent read, write, or forget? |
| 8 | Agent Communication | How do agents talk to each other? |
| 9 | Failure Recovery | What happens when something goes wrong? |
| 10 | Future Multi-Agent Scaling | How does this architecture grow from 8 agents to 800? |
| Appendix A | Agent Capability Matrix | The single reference for permissions and governance |

---

# Part 1 — Agent Philosophy

---

## 1.1 The Problem With Vague Language

Software systems fail not because engineers are careless, but because they use the same word to mean six different things. Before the first line of agent code is written, SaathiAI must define its vocabulary precisely.

The word "agent" appears in six different contexts in AI systems engineering. Without precise definitions, an engineer who hears "build an agent for this" might build an API wrapper. Another might build a full autonomous loop. A third might build a sub-component with no loop at all. All three would use the word "agent" correctly by casual standards — and all three would create an incompatible architecture.

This part eliminates that problem.

---

## 1.2 Definitions

### Assistant

A language model invocation that receives a prompt and returns a response. Single input, single output, no loop, no memory, no tools, no decision-making beyond what fits in one context window.

**Key properties:**
- Stateless (forgets everything after each call)
- No tools
- No persistent memory
- No external actions

**Example in SaathiAI:** `llm.complete(prompt, model="standard")` called directly in a router function to generate a one-off text output.

**When to use:** Content generation, text classification, summarization — any task that can be fully defined in a single prompt and does not require tool use, external state, or follow-up actions.

---

### Agent

A system that combines an LLM with tools and memory to pursue a goal across multiple steps. An agent can take actions, observe their outcomes, and adjust its behavior based on those observations.

**Key properties:**
- Stateful (maintains working memory within a session)
- Has access to tools
- Can make decisions based on tool outputs
- Operates within a defined scope
- Has a defined start and end state

**Example in SaathiAI:** The Writing Sub-Agent. It receives an IELTS writing task, uses the evaluation tool, observes the score, uses a feedback generation tool, and returns structured feedback. It loops until the task is complete or a failure condition is met.

**When to use:** Multi-step tasks where the output of one step determines the next step.

---

### Autonomous Agent

An agent that operates without human input across an extended time horizon. An autonomous agent monitors its environment, decides when to act, executes multi-step plans, and reports outcomes — without being invoked by a human for each cycle.

**Key properties:**
- Triggered by schedule or event, not human request
- Extended operation (hours, days)
- Self-monitoring and self-correcting
- Reports to Mission Control, not to a human in real-time
- Subject to higher safety classification requirements (Part 6)

**Example in SaathiAI:** The Content Scheduler. It wakes up daily at 7:00 AM, researches trending topics, selects content from the queue, generates and publishes a post, logs the result, and sleeps. No human interaction required.

**When to use:** Operational tasks that must happen on a schedule or in response to system events.

---

### Department

A logical grouping of agents that share a capability domain. A department is not a single agent — it is the organizational unit that owns a set of capabilities and delegates work to sub-agents.

**Key properties:**
- Has a head agent (the Department Director)
- Owns a set of capabilities listed in SES-000F
- Sub-agents within the department are specialized for specific tasks
- Communicates with other departments through defined interfaces, not directly with sub-agents of other departments

**Example in SaathiAI:** The Research Department. Its Director delegates to sub-agents for web search, content extraction, and synthesis. The Studio Department does not call the Research Department's web search sub-agent directly — it calls the Research Director, which routes internally.

**When to use:** When a capability domain is complex enough to require multiple specialized agents.

---

### Workflow

A defined sequence of agent actions, tool calls, and decision points that produces a specific outcome. A workflow is the design artifact; agents execute it.

**Key properties:**
- Defined start, defined end
- Explicit decision points (conditional branches)
- Measurable output
- Can be triggered manually or by schedule
- Can span multiple departments

**Example in SaathiAI:** The Daily Content Pipeline. Start → Research trending topics → Select from content calendar → Generate script → Generate captions → Render video → Schedule for 8 PM → Log result → End.

**When to use:** Any multi-department process that must be repeatable, auditable, and testable.

---

### Tool

A discrete, deterministic function that an agent can call to interact with the world. A tool has no agency — it executes exactly what it is told and returns a result.

**Key properties:**
- Deterministic (same inputs → same outputs)
- Single responsibility (one thing, done well)
- No internal decision-making
- Registered in the Tool Registry (Part 5)
- Subject to safety classification (Part 6)

**Example in SaathiAI:** `research_web(query: str, max_results: int) -> ResearchResult`. It searches the web and returns results. It does not decide what to search for, how to use the results, or what to do next.

**When to use:** For any atomic interaction with the world — file systems, databases, external APIs, user interfaces.

---

## 1.3 The Hierarchy

```
Autonomous Agents (schedule-driven, long-running)
    │
    ▼
Departments (capability owners)
    │
    ▼
Agents (goal-directed, multi-step)
    │
    ▼
Assistants (single-turn LLM calls)
    │
    ▼
Tools (atomic world interactions)
    │
    ▼
Workflows (cross-agent coordination)
```

A **workflow** is the only construct that cuts across all levels. A workflow can invoke an autonomous agent, which invokes a department, which routes to an agent, which calls tools and assistants. The workflow is the script; everything else is an actor.

---

## 1.4 Design Principles for Agents

### Principle A-1: Single Responsibility

An agent has one clearly stated purpose. If an agent's purpose requires the word "and" to describe, it needs to be split into two agents.

### Principle A-2: Explicit Contracts

Every agent declares its contract (Part 4). An agent without a written contract is not a finished agent.

### Principle A-3: Fail Loudly

An agent that encounters a failure it cannot recover from escalates immediately. Silent failures are architectural violations. An agent that swallows an error and returns a fabricated result is worse than one that fails visibly.

### Principle A-4: Observable

Every significant action is traced. Every event is emitted. An agent that operates silently is ungovernable.

### Principle A-5: Tool-First

An agent that needs to interact with the world uses a tool. It does not make direct API calls, import SDKs, or write to databases directly. This preserves safety classification, audit logging, and retry behavior.

### Principle A-6: Memory-Aware

An agent reads the relevant context before acting. An agent that starts every cycle from scratch, ignoring accumulated knowledge, is not intelligent — it is expensive.

### Principle A-7: Bounded Scope

An agent operates within its department's capability domain. An agent that reaches into another department's capabilities without routing through that department's director is an architectural violation.

---

# Part 2 — BMA Loop

**BMA** = Baadar Multi-Agent Architecture. The BMA loop is SaathiAI's cognitive engine — the cycle every agent runs when it needs to do something non-trivial.

---

## 2.1 The Loop

```
┌─────────────────────────────────────────────────────────────────────┐
│                         BMA LOOP                                    │
│                                                                     │
│  ┌──────────┐    ┌────────────┐    ┌──────────┐    ┌────────────┐  │
│  │  OBSERVE │ ──►│ UNDERSTAND │ ──►│  REASON  │ ──►│    PLAN    │  │
│  └──────────┘    └────────────┘    └──────────┘    └────────────┘  │
│       ▲                                                    │        │
│       │                                                    ▼        │
│  ┌───────────┐  ┌──────────┐  ┌─────────┐   ┌──────────────────┐  │
│  │  UPDATE   │◄─│  LEARN   │◄─│EVALUATE │◄──│     EXECUTE      │  │
│  │  MEMORY   │  └──────────┘  └─────────┘   └──────────────────┘  │
│  └───────────┘                                        │            │
│                                                       ▼            │
│                                               ┌────────────┐       │
│                                               │   VERIFY   │       │
│                                               └────────────┘       │
└─────────────────────────────────────────────────────────────────────┘
```

The loop runs until one of three terminal conditions:
1. **Goal achieved** — the agent's objective is met and verified
2. **Max cycles exceeded** — a configurable cycle limit is reached (default: 10)
3. **Unrecoverable failure** — Part 9 failure recovery is exhausted

---

## 2.2 Phase Specifications

---

### Phase 1 — OBSERVE

**Purpose:** Gather all relevant context before acting.

**Inputs:**
- Trigger (user message, scheduled event, agent-to-agent request, event from AgentMessageBus)
- Working Memory (current session deque, up to 20 messages)
- Episodic Memory snapshot (last N relevant interactions)
- Semantic context (patterns relevant to the current task, if available)
- Platform state (current scheduler jobs, service health, pending notifications)

**Processing:**
```python
class ObservePhase:
    def run(self, trigger: AgentTrigger) -> ObserveResult:
        context = ObserveResult(
            trigger=trigger,
            working_memory=self.memory.working.get_all(),
            episodic_context=self.memory.episodic.get_relevant(
                trigger.intent, limit=10
            ),
            semantic_context=self.memory.semantic.search(
                trigger.content, top_k=5
            ) if self.memory.semantic.available else [],
            platform_state=self.platform.get_state(),
        )
        self.bus.emit(BMAEvent(
            type="phase.observe.complete",
            agent=self.name,
            payload={"context_size": context.token_estimate()}
        ))
        return context
```

**Outputs:** `ObserveResult` containing all gathered context

**Failure handling:**
- If memory system is unavailable: proceed with empty context, emit `WARNING: memory_unavailable`
- If platform state is unavailable: proceed with last known state, log warning
- Never fail the OBSERVE phase — degraded context is better than no context

**Events emitted:** `phase.observe.complete`

**Memory interactions:** Reads Working Memory, Episodic Memory, Semantic Memory

---

### Phase 2 — UNDERSTAND

**Purpose:** Parse the trigger into a structured task with clear goals, constraints, and success criteria.

**Inputs:** `ObserveResult` from Phase 1

**Processing:**

The UNDERSTAND phase runs a `screening` model call to classify the request before committing to the more expensive reasoning model. This is the "fast triage" before the "deep think."

```python
class UnderstandPhase:
    def run(self, observe: ObserveResult) -> UnderstandResult:
        # Fast classification with screening model
        classification = await llm.complete(
            prompt=UNDERSTAND_CLASSIFY_PROMPT.format(
                content=observe.trigger.content,
                context_summary=observe.working_memory_summary()
            ),
            model="screening",
            max_tokens=200
        )

        task = UnderstandResult(
            intent=classification.intent,
            goal=classification.goal,
            constraints=classification.constraints,
            success_criteria=classification.success_criteria,
            required_departments=classification.route_to,
            estimated_complexity=classification.complexity,  # simple|medium|complex
            requires_approval=classification.requires_approval,
        )

        self.bus.emit(BMAEvent(
            type="phase.understand.complete",
            agent=self.name,
            payload={"intent": task.intent, "complexity": task.estimated_complexity}
        ))
        return task
```

**Outputs:** `UnderstandResult` with structured task definition

**Failure handling:**
- If classification returns empty or unparseable: retry once with `standard` model
- If second attempt fails: escalate to human with `NEEDS_CONTEXT` status
- If intent is ambiguous: do not guess — emit `phase.understand.ambiguous` and request clarification

**Events emitted:** `phase.understand.complete`, `phase.understand.ambiguous` (conditional)

**Memory interactions:** Reads Working Memory summary

---

### Phase 3 — REASON

**Purpose:** Determine the best approach to the task. This is the agent's deliberative phase — it thinks before it acts.

**Inputs:** `UnderstandResult` from Phase 2, full `ObserveResult`

**Processing:**

The REASON phase selects the model based on task complexity:
- `simple` → `standard` model
- `medium` → `standard` model with chain-of-thought
- `complex` → `reasoning` model (Claude)

```python
class ReasonPhase:
    def run(
        self, understand: UnderstandResult, observe: ObserveResult
    ) -> ReasonResult:
        model = self._select_model(understand.estimated_complexity)

        reasoning = await llm.complete(
            prompt=REASON_PROMPT.format(
                goal=understand.goal,
                constraints=understand.constraints,
                success_criteria=understand.success_criteria,
                context=observe.episodic_context,
                available_tools=self.tool_registry.list_for_agent(self.name),
            ),
            model=model,
            system=AGENT_SYSTEM_PROMPT.format(
                agent_name=self.name,
                agent_purpose=self.contract.purpose
            ),
            max_tokens=1000
        )

        self.bus.emit(BMAEvent(
            type="phase.reason.complete",
            agent=self.name,
            payload={"model_used": model, "approach": reasoning.approach_summary}
        ))
        return reasoning
```

**Outputs:** `ReasonResult` with:
- Selected approach
- Tools required
- Risk assessment
- Whether human approval is needed before proceeding

**Failure handling:**
- If reasoning model returns incoherent output: retry once with `reasoning` model regardless of complexity
- If three reasoning attempts fail: return `BLOCKED` status, escalate to human

**Events emitted:** `phase.reason.complete`

**Memory interactions:** Reads Episodic Memory for similar past approaches

---

### Phase 4 — PLAN

**Purpose:** Translate the reasoning into a concrete, ordered list of executable steps.

**Inputs:** `ReasonResult`, `UnderstandResult`

**Processing:**

```python
class PlanPhase:
    def run(
        self, reason: ReasonResult, understand: UnderstandResult
    ) -> ExecutionPlan:
        steps = []
        for step_spec in reason.steps:
            step = ExecutionStep(
                index=step_spec.index,
                tool_name=step_spec.tool,
                parameters=step_spec.parameters,
                safety_level=self.safety.classify(
                    step_spec.tool, step_spec.parameters
                ),
                requires_approval=step_spec.requires_approval or
                    self.safety.requires_approval(step_spec.tool),
                on_failure=step_spec.on_failure,  # retry|skip|abort|escalate
                timeout_seconds=step_spec.timeout or
                    self.tool_registry.get_timeout(step_spec.tool),
            )
            steps.append(step)

        plan = ExecutionPlan(
            steps=steps,
            total_steps=len(steps),
            estimated_duration_seconds=sum(s.timeout_seconds for s in steps),
            has_critical_steps=any(
                s.safety_level == SafetyLevel.CRITICAL for s in steps
            ),
        )

        # Gate: if any critical steps, require approval before execution
        if plan.has_critical_steps and not understand.pre_approved:
            plan.status = PlanStatus.AWAITING_APPROVAL

        self.bus.emit(BMAEvent(
            type="phase.plan.complete",
            agent=self.name,
            payload={
                "steps": len(steps),
                "has_critical": plan.has_critical_steps,
                "status": plan.status
            }
        ))
        return plan
```

**Outputs:** `ExecutionPlan` — ordered list of `ExecutionStep` objects

**Failure handling:**
- If a required tool is not in the registry: abort with `TOOL_NOT_FOUND` error
- If safety classification fails: treat as `CRITICAL` and require approval
- If plan is empty (no steps needed): proceed directly to EVALUATE with no-op result

**Events emitted:** `phase.plan.complete`, `phase.plan.awaiting_approval` (conditional)

**Memory interactions:** None (planning is stateless)

---

### Phase 5 — EXECUTE

**Purpose:** Run the plan, step by step, calling tools and handling outcomes.

**Inputs:** `ExecutionPlan` from Phase 4

**Processing:**

```python
class ExecutePhase:
    async def run(self, plan: ExecutionPlan) -> ExecuteResult:
        results = []

        for step in plan.steps:
            if step.requires_approval:
                approved = await self._request_approval(step)
                if not approved:
                    results.append(StepResult(
                        step=step, status="rejected", output=None
                    ))
                    if step.on_failure == "abort":
                        break
                    continue

            self.bus.emit(BMAEvent(
                type="tool.invoked",
                agent=self.name,
                payload={"tool": step.tool_name, "step": step.index}
            ))

            try:
                output = await asyncio.wait_for(
                    self.tool_registry.execute(
                        step.tool_name, step.parameters
                    ),
                    timeout=step.timeout_seconds
                )

                self.bus.emit(BMAEvent(
                    type="tool.completed",
                    agent=self.name,
                    payload={
                        "tool": step.tool_name,
                        "step": step.index,
                        "success": True
                    }
                ))
                results.append(StepResult(
                    step=step, status="completed", output=output
                ))

            except (asyncio.TimeoutError, ToolError) as e:
                result = await self._handle_step_failure(step, e)
                results.append(result)
                if result.status == "abort":
                    break

        return ExecuteResult(
            steps=results,
            all_completed=all(r.status == "completed" for r in results),
            any_failed=any(r.status in ("failed", "abort") for r in results),
        )
```

**Outputs:** `ExecuteResult` with per-step results

**Failure handling:** See Part 9 — Failure Recovery for the complete policy.

**Events emitted:** `tool.invoked`, `tool.completed`, `tool.failed` (per step)

**Memory interactions:** Writes tool outputs to Working Memory after each step

---

### Phase 6 — VERIFY

**Purpose:** Confirm that the execution results actually satisfy the goal.

**Inputs:** `ExecuteResult`, `UnderstandResult.success_criteria`

**Processing:**

This phase does not trust that "completed" means "correct." It checks the outputs against the success criteria defined in UNDERSTAND.

```python
class VerifyPhase:
    async def run(
        self, execute: ExecuteResult, criteria: list[SuccessCriterion]
    ) -> VerifyResult:
        if not execute.all_completed:
            return VerifyResult(
                passed=False,
                reason="Not all steps completed",
                retry_recommended=True,
                failed_criteria=[c for c in criteria]
            )

        verification = await llm.complete(
            prompt=VERIFY_PROMPT.format(
                success_criteria=criteria,
                execution_results=execute.summary(),
            ),
            model="standard",
            max_tokens=500
        )

        self.bus.emit(BMAEvent(
            type="phase.verify.complete",
            agent=self.name,
            payload={"passed": verification.passed, "score": verification.score}
        ))
        return verification
```

**Outputs:** `VerifyResult` — pass/fail with reasons and retry recommendation

**Failure handling:**
- If verification itself fails: treat as VERIFY_FAILED and escalate
- If result is ambiguous: treat as failed, recommend retry

**Events emitted:** `phase.verify.complete`

**Memory interactions:** None

---

### Phase 7 — EVALUATE

**Purpose:** Assess the quality of the outcome beyond binary pass/fail. This is where the agent reflects on what it did well, what it did poorly, and what it would do differently.

**Inputs:** `VerifyResult`, full `ExecutionPlan`, `ExecuteResult`

**Processing:**

```python
class EvaluatePhase:
    async def run(
        self,
        verify: VerifyResult,
        plan: ExecutionPlan,
        execute: ExecuteResult
    ) -> EvaluateResult:
        evaluation = await llm.complete(
            prompt=EVALUATE_PROMPT.format(
                original_goal=self.current_task.goal,
                planned_steps=plan.summary(),
                executed_results=execute.summary(),
                verify_result=verify.summary(),
            ),
            model="standard",
            max_tokens=600
        )

        self.bus.emit(BMAEvent(
            type="phase.evaluate.complete",
            agent=self.name,
            payload={
                "quality_score": evaluation.quality_score,
                "lessons": len(evaluation.lessons_learned)
            }
        ))
        return evaluation
```

**Outputs:** `EvaluateResult` with:
- Quality score (0.0–1.0)
- What went well
- What went wrong
- Lessons learned (structured for LEARN phase)
- Recommendations for similar future tasks

**Failure handling:**
- If evaluation model call fails: emit warning, skip LEARN phase, proceed to UPDATE_MEMORY with partial data

**Events emitted:** `phase.evaluate.complete`

**Memory interactions:** None (input phase for LEARN)

---

### Phase 8 — LEARN

**Purpose:** Extract durable lessons from the evaluation and prepare them for memory storage.

**Inputs:** `EvaluateResult`

**Processing:**

```python
class LearnPhase:
    def run(self, evaluate: EvaluateResult) -> LearnResult:
        learnings = []
        for lesson in evaluate.lessons_learned:
            learning = Learning(
                pattern_key=lesson.key,
                pattern_value=lesson.value,
                confidence=lesson.confidence,
                source_agent=self.name,
                source_task=self.current_task.intent,
                applicable_when=lesson.trigger_condition,
            )
            learnings.append(learning)

        self.bus.emit(BMAEvent(
            type="phase.learn.complete",
            agent=self.name,
            payload={"learnings_generated": len(learnings)}
        ))
        return LearnResult(learnings=learnings)
```

**Outputs:** `LearnResult` — list of structured `Learning` objects ready for memory

**Failure handling:** Non-critical. If LEARN fails, log warning and proceed. Learnings are valuable but not required for task completion.

**Events emitted:** `phase.learn.complete`

**Memory interactions:** Prepares data for UPDATE_MEMORY (no direct write here)

---

### Phase 9 — UPDATE MEMORY

**Purpose:** Persist the interaction, outcomes, and learnings to the appropriate memory tier.

**Inputs:** `LearnResult`, `ExecuteResult`, `VerifyResult`, full cycle context

**Processing:**

```python
class UpdateMemoryPhase:
    async def run(
        self,
        learn: LearnResult,
        execute: ExecuteResult,
        verify: VerifyResult,
    ) -> None:
        # 1. Log to Episodic Memory
        await self.memory.episodic.log(EpisodicEntry(
            agent=self.name,
            intent=self.current_task.intent,
            tools_used=[r.step.tool_name for r in execute.steps],
            outcome="success" if verify.passed else "failure",
            quality_score=self.current_evaluation.quality_score,
            duration_ms=self.cycle_duration_ms,
        ))

        # 2. Store learnings in Semantic Memory
        for learning in learn.learnings:
            await self.memory.semantic.store(learning)

        # 3. Update Working Memory with cycle summary
        self.memory.working.add(WorkingMemoryEntry(
            role="system",
            content=f"Cycle complete: {self.current_task.intent}. "
                    f"Result: {'success' if verify.passed else 'failure'}.",
        ))

        self.bus.emit(BMAEvent(
            type="phase.update_memory.complete",
            agent=self.name,
            payload={"episodic_logged": True, "learnings_stored": len(learn.learnings)}
        ))
```

**Outputs:** None (side effects only)

**Failure handling:**
- If Episodic write fails: retry once, then log to fallback SQLite table `episodic_memory_fallback`
- If Semantic write fails: log warning, do not retry (learnings will be regenerated next time)

**Events emitted:** `phase.update_memory.complete`, `cycle.complete`

**Memory interactions:** Writes to all three memory tiers

---

## 2.3 Cycle Lifecycle Events

The complete set of events a single BMA cycle emits, in order:

| Event | Phase | Consumers |
|-------|-------|----------|
| `cycle.started` | (before Phase 1) | Observability, Mission Control |
| `phase.observe.complete` | Phase 1 | Observability |
| `phase.understand.complete` | Phase 2 | Observability, Router |
| `phase.understand.ambiguous` | Phase 2 (conditional) | Mission Control, Human |
| `phase.reason.complete` | Phase 3 | Observability |
| `phase.plan.complete` | Phase 4 | Observability |
| `phase.plan.awaiting_approval` | Phase 4 (conditional) | Human/Mission Control |
| `tool.invoked` | Phase 5 (per step) | SafetyHarness, Observability |
| `tool.completed` | Phase 5 (per step) | Memory, Observability |
| `tool.failed` | Phase 5 (conditional) | Failure Recovery, Notification |
| `phase.verify.complete` | Phase 6 | Observability |
| `phase.evaluate.complete` | Phase 7 | Observability |
| `phase.learn.complete` | Phase 8 | Observability |
| `phase.update_memory.complete` | Phase 9 | Observability |
| `cycle.complete` | Phase 9 | Analytics, Mission Control, Observability |
| `cycle.failed` | Phase 9 (conditional) | Notification, Mission Control |

---

## 2.4 Cycle Configuration

```python
class BMAConfig(BaseModel):
    max_cycles: int = 10
    max_tokens_per_phase: int = 2000
    require_verify: bool = True
    require_evaluate: bool = True
    require_learn: bool = True
    approval_timeout_seconds: int = 300   # 5 minutes for human approval
    tool_timeout_default_seconds: int = 30
    memory_working_maxlen: int = 20
```

---

# Part 3 — Department Hierarchy

---

## 3.1 Why Departments

Agents that report to nothing are ungovernable. Capabilities that belong to no one are duplicated or abandoned.

The Department structure gives SaathiAI an organizational model that mirrors how human organizations work: each department owns a domain, has a director who routes work internally, and communicates with other departments through defined interfaces.

This has a practical engineering benefit: when a new capability is needed, the question "which department owns this?" has a deterministic answer. If no department owns it, a new department is created. If two departments claim it, the architecture has a conflict that must be resolved before implementation.

---

## 3.2 The Department Hierarchy

```
╔════════════════════════════════════════════════════════════╗
║                    CEO AGENT                               ║
║  Strategic direction, cross-department coordination,       ║
║  resource allocation, mission-level decisions              ║
╚═════════════════════════┬══════════════════════════════════╝
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
╔═══════▼═══════╗  ╔══════▼═══════╗  ╔═════▼══════════╗
║   PLANNING    ║  ║   RESEARCH   ║  ║  ENGINEERING   ║
║   DEPT        ║  ║   DEPT       ║  ║  DEPT          ║
║               ║  ║              ║  ║                ║
║ Goal setting  ║  ║ Web research ║  ║ Code execution ║
║ Roadmapping   ║  ║ Signal mon.  ║  ║ File ops       ║
║ Scheduling    ║  ║ Synthesis    ║  ║ DB ops         ║
╚═══════════════╝  ╚══════════════╝  ╚════════════════╝
        │                 │                 │
        └─────────────────┼─────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
╔═══════▼═══════╗  ╔══════▼═══════╗  ╔═════▼══════════╗
║    VOICE      ║  ║   STUDIO     ║  ║   QA DEPT      ║
║    DEPT       ║  ║   DEPT       ║  ║                ║
║               ║  ║              ║  ║                ║
║ STT / TTS     ║  ║ Content gen  ║  ║ Evaluation     ║
║ Voice clone   ║  ║ Video render ║  ║ Verification   ║
║ Voice session ║  ║ Publishing   ║  ║ Safety check   ║
╚═══════════════╝  ╚══════════════╝  ╚════════════════╝
                          │
                ╔═════════▼════════╗
                ║ MISSION CONTROL  ║
                ║                  ║
                ║ Platform health  ║
                ║ Operator alerts  ║
                ║ Telegram I/O     ║
                ╚══════════════════╝
```

---

## 3.3 Department Capability Ownership

| Department | Capabilities Owned (CAP-XXX) | SES Document |
|------------|------------------------------|-------------|
| CEO | Strategic planning, resource allocation, cross-dept coordination | SES-002 (this doc) |
| Planning | CAP-005 Scheduler, goal decomposition, roadmap maintenance | SES-002 |
| Research | CAP-030 Research Engine, CAP-031 Signal Monitor | SES-006 |
| Engineering | Code execution, file operations, database operations, deployment | SES-002 |
| Voice | CAP-010 STT, CAP-011 TTS, CAP-012 Voice Clone | SES-004 |
| Studio | CAP-020 Content Generator, CAP-021 Video Renderer, CAP-022 Social Publisher | SES-005 |
| QA | CAP-006 Evaluation Engine, verification, safety assessment | SES-002 |
| Mission Control | Platform health, operator communication, alert management | SES-009 |

---

## 3.4 Communication Rules

1. **Department-to-Department:** Always through the Department Director agent. Never directly to a sub-agent of another department.
2. **Department-to-CEO:** Directors report to the CEO agent for strategic decisions, resource requests, and cross-department conflicts.
3. **CEO-to-Department:** The CEO routes tasks to a specific department. It does not implement work itself.
4. **Mission Control is read-only by default.** Other departments publish events; Mission Control consumes them. Mission Control initiates communication only for alerts and operator commands.

---

## 3.5 Sub-Agent Registry by Department

### CEO Department
| Agent | Purpose |
|-------|---------|
| `ceo_agent` | Strategic direction, cross-department coordination |

### Planning Department
| Agent | Purpose |
|-------|---------|
| `planner_agent` | Director — receives goals, creates execution plans |
| `scheduler_agent` | Manages APScheduler jobs and timing |
| `roadmap_agent` | Maintains platform roadmap and priorities (Phase 2) |

### Research Department
| Agent | Purpose |
|-------|---------|
| `research_director` | Director — routes research tasks |
| `web_search_agent` | Executes web searches and extracts content |
| `signal_monitor_agent` | Monitors registered signals continuously |
| `synthesis_agent` | Synthesizes multi-source research into reports |

### Engineering Department
| Agent | Purpose |
|-------|---------|
| `engineering_director` | Director — routes engineering tasks |
| `code_agent` | Reads and executes code operations |
| `database_agent` | Database queries and schema operations |
| `file_agent` | File system read/write operations |

### Voice Department
| Agent | Purpose |
|-------|---------|
| `voice_director` | Director — routes voice tasks |
| `stt_agent` | Speech-to-text transcription |
| `tts_agent` | Text-to-speech synthesis |
| `voice_clone_agent` | Voice profile management |

### Studio Department
| Agent | Purpose |
|-------|---------|
| `studio_director` | Director — routes content and publishing tasks |
| `content_agent` | Generates text content (scripts, captions, posts) |
| `video_agent` | Renders videos using HyperFrames |
| `publish_agent` | Publishes to social platforms |

### QA Department
| Agent | Purpose |
|-------|---------|
| `qa_director` | Director — routes evaluation and verification tasks |
| `evaluator_agent` | General rubric-based evaluation |
| `ielts_evaluator` | IELTS-specific band score evaluation (pielts) |
| `safety_agent` | Reviews pending actions against safety policy |

### Mission Control Department
| Agent | Purpose |
|-------|---------|
| `mission_control` | Platform health monitoring and operator interface |
| `alert_agent` | Generates and routes alerts |
| `telegram_agent` | Manages two-way Telegram communication |

---

## 3.6 How a Task Flows Through the Hierarchy

Example: "Publish a Mr. Yeti IELTS tip video today."

```
1. Operator → Telegram → telegram_agent → mission_control
2. mission_control → ceo_agent (strategic routing)
3. ceo_agent → planner_agent (task decomposition)
4. planner_agent creates workflow:
   Step A: research_director → web_search_agent (trending IELTS topics)
   Step B: studio_director → content_agent (write script)
   Step C: studio_director → video_agent (render video)
   Step D: qa_director → evaluator_agent (check quality)
   Step E: studio_director → publish_agent (publish video)
5. Each step runs as a BMA cycle within its assigned agent
6. Results flow back up: publish_agent → studio_director → planner_agent → ceo_agent
7. ceo_agent → mission_control → telegram_agent → Operator
```

---

# Part 4 — Agent Contract

---

## 4.1 The Contract

Every agent in SaathiAI must declare a complete contract before implementation begins. A contract defines what the agent is, what it owns, and how it behaves. An agent without a contract is not an agent — it is a function that got promoted above its station.

The contract is the agent's API. It is the document other agents read to decide whether to delegate to this agent. It is the document QA reads to write tests. It is the document Mission Control reads to generate meaningful alerts.

---

## 4.2 Contract Schema

```python
class AgentContract(BaseModel):
    # Identity
    name: str                          # snake_case identifier
    display_name: str                  # Human-readable name
    version: str                       # semver
    department: DepartmentName
    parent_agent: str | None           # None for department directors
    
    # Purpose (the four-question contract from SES-001)
    purpose: str                       # ONE sentence. If it needs "and", split the agent.
    why_it_exists: str                 # What gap it fills that no other agent fills
    capabilities_owned: list[str]      # CAP-XXX IDs from SES-000F
    interfaces_exposed: list[str]      # API paths or bus event types
    dependents: list[str]              # Which agents may depend on this one
    
    # Behavior
    inputs: list[InputSpec]            # What it accepts
    outputs: list[OutputSpec]          # What it produces
    tools: list[str]                   # Tool names it may call (from Tool Registry)
    
    # Memory
    memory_read: MemoryAccessSpec      # What memory tiers it may read
    memory_write: MemoryAccessSpec     # What memory tiers it may write
    
    # Communication
    events_published: list[str]        # Bus event types it emits
    events_consumed: list[str]         # Bus event types it reacts to
    
    # Safety and approval
    safety_level: SafetyLevel          # Read|Write|Modify|External|Critical
    approval_required_for: list[str]   # Specific actions requiring human approval
    human_escalation_triggers: list[str] # Conditions that escalate to human
    
    # Failure
    failure_policy: FailurePolicy      # How it handles each failure type
    max_cycles: int = 10
    
    # Measurement
    kpis: list[KPISpec]               # How success is measured
    sla_seconds: int | None           # Response time SLA
```

---

## 4.3 Reference Contract: `content_agent`

```python
AgentContract(
    name="content_agent",
    display_name="Content Generator",
    version="1.0.0",
    department="studio",
    parent_agent="studio_director",

    purpose="Generate platform content (scripts, captions, blog posts, social copy) from a brief.",
    why_it_exists="Centralizes all text content generation so tone and format are consistent across products.",
    capabilities_owned=["CAP-020"],
    interfaces_exposed=["POST /api/v1/studio/content"],
    dependents=["video_agent", "publish_agent", "planner_agent"],

    inputs=[
        InputSpec(name="brief", type="ContentBrief", required=True),
        InputSpec(name="persona", type="PersonaProfile", required=False),
        InputSpec(name="format", type="ContentFormat", required=True),
    ],
    outputs=[
        OutputSpec(name="content", type="GeneratedContent"),
        OutputSpec(name="metadata", type="ContentMetadata"),
    ],
    tools=[
        "generate_content",
        "get_persona_profile",
        "check_content_calendar",
        "search_memory",
    ],

    memory_read=MemoryAccessSpec(
        working=True,
        episodic=True,     # reads past content for tone consistency
        semantic=True,     # reads style patterns
    ),
    memory_write=MemoryAccessSpec(
        working=True,
        episodic=True,     # logs generated content
        semantic=False,    # does not write patterns (QA dept does this)
    ),

    events_published=["content.generated", "content.failed"],
    events_consumed=["cycle.started"],

    safety_level=SafetyLevel.WRITE,  # generates content, does not publish
    approval_required_for=[],         # content generation needs no approval
    human_escalation_triggers=[
        "three_consecutive_failures",
        "content_policy_violation_detected",
    ],

    failure_policy=FailurePolicy(
        tool_failure="retry_once_then_skip",
        llm_failure="retry_with_reasoning_model",
        timeout="abort_and_log",
        invalid_output="retry_with_clarification",
    ),
    max_cycles=5,

    kpis=[
        KPISpec(metric="content_quality_score", target=0.8, unit="score_0_to_1"),
        KPISpec(metric="generation_latency_ms", target=3000, unit="ms"),
        KPISpec(metric="content_rejection_rate", target=0.05, unit="rate_0_to_1"),
    ],
    sla_seconds=10,
)
```

---

## 4.4 Contract Validation

Before an agent runs in production, its contract is validated:

```python
def validate_contract(contract: AgentContract) -> list[ContractViolation]:
    violations = []

    # Purpose must not contain "and" (single responsibility)
    if " and " in contract.purpose.lower():
        violations.append(ContractViolation(
            field="purpose",
            message="Purpose contains 'and' — split into two agents."
        ))

    # All tools must be registered
    for tool in contract.tools:
        if tool not in TOOL_REGISTRY:
            violations.append(ContractViolation(
                field="tools",
                message=f"Tool '{tool}' not in registry."
            ))

    # All capabilities must be in SES-000F
    for cap in contract.capabilities_owned:
        if cap not in CAPABILITY_REGISTRY:
            violations.append(ContractViolation(
                field="capabilities_owned",
                message=f"Capability '{cap}' not registered in SES-000F."
            ))

    # KPIs must have targets
    for kpi in contract.kpis:
        if kpi.target is None:
            violations.append(ContractViolation(
                field="kpis",
                message=f"KPI '{kpi.metric}' has no target."
            ))

    return violations
```

---

# Part 5 — Tool Registry

---

## 5.1 The Role of the Tool Registry

Every tool available to every agent is registered in one place: `app/tools/registry.py`. No agent calls a function that is not in the registry. This is not a suggestion — it is enforced at import time.

The registry provides:
1. **Discovery** — agents can query available tools by category or permission level
2. **Safety enforcement** — the SafetyHarness reads tool metadata to classify actions
3. **Audit logging** — every tool invocation is logged with the tool's declared side effects
4. **Timeout enforcement** — the executor uses the tool's declared timeout
5. **Retry policy** — automatic retry based on the tool's declared retryability

---

## 5.2 Tool Metadata Schema

```python
class ToolMetadata(BaseModel):
    # Identity
    name: str                          # snake_case, unique in registry
    display_name: str
    version: str
    category: ToolCategory             # research|communication|content|data|system
    module_path: str                   # app/tools/<category>/<name>.py
    
    # Declaration
    description: str                   # One sentence: what it does
    parameters: list[ToolParameter]    # Typed parameter definitions
    return_type: str                   # Python type hint as string
    
    # Safety
    safety_level: SafetyLevel          # Read|Write|Modify|External|Critical
    side_effects: list[str]            # Explicit list of what it changes
    requires_approval: bool = False    # Override: always require approval
    audit_logging: AuditLevel          # none|summary|full
    
    # Reliability
    timeout_seconds: int = 30
    is_retryable: bool = True
    max_retries: int = 3
    retry_on: list[str]                # Exception class names that trigger retry
    
    # Permissions
    allowed_agents: list[str] | None = None  # None = all agents
    denied_agents: list[str] = []
    
    # Dependencies
    requires_env: list[str] = []       # Environment variables required
    requires_service: list[str] = []   # External services required (e.g., "omnivoice")
```

---

## 5.3 Reference Tool Entry: `research_web`

```python
ToolMetadata(
    name="research_web",
    display_name="Web Research",
    version="1.0.0",
    category=ToolCategory.RESEARCH,
    module_path="app/tools/research/research_web.py",

    description="Search the web and return structured content from matching pages.",
    parameters=[
        ToolParameter(name="query", type="str", required=True,
                      description="Search query"),
        ToolParameter(name="max_results", type="int", required=False,
                      default=5, description="Maximum results to return"),
        ToolParameter(name="extract_content", type="bool", required=False,
                      default=True, description="Extract full page content"),
    ],
    return_type="ResearchResult",

    safety_level=SafetyLevel.READ,
    side_effects=[],                   # Read-only, no side effects
    requires_approval=False,
    audit_logging=AuditLevel.SUMMARY,

    timeout_seconds=30,
    is_retryable=True,
    max_retries=3,
    retry_on=["SearchProviderError", "TimeoutError"],

    allowed_agents=None,               # All agents may use this
    denied_agents=[],

    requires_env=["BRAVE_API_KEY"],
    requires_service=[],
)
```

---

## 5.4 Reference Tool Entry: `send_telegram`

```python
ToolMetadata(
    name="send_telegram",
    display_name="Send Telegram Message",
    version="1.0.0",
    category=ToolCategory.COMMUNICATION,
    module_path="app/tools/communication/send_telegram.py",

    description="Send a message to the operator's Telegram chat.",
    parameters=[
        ToolParameter(name="message", type="str", required=True),
        ToolParameter(name="parse_mode", type="str", required=False,
                      default="Markdown"),
    ],
    return_type="TelegramResult",

    safety_level=SafetyLevel.EXTERNAL,
    side_effects=["sends_external_message", "charges_telegram_api"],
    requires_approval=False,           # Routine notifications don't need approval
    audit_logging=AuditLevel.FULL,

    timeout_seconds=15,
    is_retryable=True,
    max_retries=2,
    retry_on=["TelegramNetworkError"],

    allowed_agents=["mission_control", "alert_agent", "telegram_agent",
                    "planner_agent"],
    denied_agents=[],

    requires_env=["TELEGRAM_BOT_TOKEN"],
    requires_service=["telegram"],
)
```

---

## 5.5 Reference Tool Entry: `deploy_to_production`

```python
ToolMetadata(
    name="deploy_to_production",
    display_name="Deploy to Production",
    version="1.0.0",
    category=ToolCategory.SYSTEM,
    module_path="app/tools/system/deploy_to_production.py",

    description="Deploy the platform to the production environment.",
    parameters=[
        ToolParameter(name="version", type="str", required=True),
        ToolParameter(name="confirm", type="bool", required=True),
    ],
    return_type="DeployResult",

    safety_level=SafetyLevel.CRITICAL,
    side_effects=[
        "modifies_production_environment",
        "potentially_interrupts_service",
        "irreversible_without_rollback",
    ],
    requires_approval=True,            # ALWAYS requires operator approval
    audit_logging=AuditLevel.FULL,

    timeout_seconds=300,
    is_retryable=False,                # Deploy is not automatically retried
    max_retries=0,
    retry_on=[],

    allowed_agents=["engineering_director", "ceo_agent"],
    denied_agents=[
        "content_agent", "publish_agent", "synthesis_agent",
        "web_search_agent", "tts_agent", "stt_agent",
    ],

    requires_env=["DEPLOY_KEY"],
    requires_service=["production_server"],
)
```

---

## 5.6 Registry Access Patterns

```python
# List all tools an agent may use
tools = TOOL_REGISTRY.list_for_agent("content_agent")

# Get tool metadata
meta = TOOL_REGISTRY.get("research_web")

# Execute a tool (goes through SafetyHarness automatically)
result = await TOOL_REGISTRY.execute(
    tool_name="research_web",
    params={"query": "IELTS writing task 2 tips", "max_results": 5},
    calling_agent="web_search_agent"
)
```

---

# Part 6 — SafetyHarness

---

## 6.1 Why SafetyHarness

Agent systems fail not by making catastrophically wrong decisions at the strategic level. They fail by making small wrong decisions at the execution level, repeatedly and quietly: a content agent that publishes draft content; a research agent that overwrites production records; a scheduler that sends 200 notifications instead of one.

The SafetyHarness is the enforcement layer between "what the agent wants to do" and "what the agent is allowed to do." It is not a suggestion system. It is a gate.

---

## 6.2 Safety Level Classification

Every tool action, database operation, and external call is classified at one of five levels:

| Level | Name | Examples | Default Handling |
|-------|------|---------|-----------------|
| L1 | **READ** | Search files, query memory, read database, fetch web page | Auto-approved |
| L2 | **WRITE** | Write to file, insert record, generate content, render video | Auto-approved |
| L3 | **MODIFY** | Update database record, overwrite file, edit configuration | Auto-approved with audit log |
| L4 | **EXTERNAL** | Send email, post to Telegram, call external API, publish to social | Auto-approved with full audit log (configurable to require approval) |
| L5 | **CRITICAL** | Deploy to production, delete records, execute shell commands, send financial transactions | Always requires explicit human approval |

---

## 6.3 Approval Decision Tree

```
Tool action requested by agent
        │
        ▼
Is the calling agent allowed to use this tool?
        │
        ├── No  ──► BLOCK. Log. Emit safety.blocked event.
        │
        ▼ Yes
Is the tool's safety level CRITICAL?
        │
        ├── Yes ──► REQUEST_HUMAN_APPROVAL. Wait up to 300 seconds.
        │               │
        │               ├── Approved ──► Execute. Log. Emit.
        │               └── Denied / Timeout ──► BLOCK. Log. Emit safety.blocked.
        │
        ▼ No
Does the tool's metadata declare requires_approval=True?
        │
        ├── Yes ──► REQUEST_HUMAN_APPROVAL. Wait. (Same as CRITICAL path)
        │
        ▼ No
Does the agent contract declare this action needs approval?
        │
        ├── Yes ──► REQUEST_HUMAN_APPROVAL.
        │
        ▼ No
Is this an EXTERNAL action with daily volume > configured threshold?
        │
        ├── Yes ──► REQUEST_HUMAN_APPROVAL.
        │
        ▼ No
Auto-approve. Execute. Log at appropriate audit level.
```

---

## 6.4 SafetyHarness Implementation

```python
class SafetyHarness:
    def __init__(self, config: SafetyConfig):
        self.config = config
        self.audit_log = AuditLogger()
        self.approval_service = ApprovalService(
            timeout_seconds=config.approval_timeout_seconds
        )

    async def check(
        self,
        tool_name: str,
        parameters: dict,
        calling_agent: str,
    ) -> SafetyDecision:
        tool = TOOL_REGISTRY.get(tool_name)
        agent_contract = AGENT_REGISTRY.get(calling_agent)

        # Check 1: Agent permission
        if calling_agent in tool.denied_agents:
            return self._block(tool, calling_agent, "agent_denied")

        if tool.allowed_agents and calling_agent not in tool.allowed_agents:
            return self._block(tool, calling_agent, "agent_not_permitted")

        # Check 2: Critical level → always require approval
        if tool.safety_level == SafetyLevel.CRITICAL:
            return await self._request_approval(
                tool, parameters, calling_agent, reason="critical_action"
            )

        # Check 3: Tool declares approval required
        if tool.requires_approval:
            return await self._request_approval(
                tool, parameters, calling_agent, reason="tool_requires_approval"
            )

        # Check 4: Agent contract requires approval for this tool
        if tool_name in agent_contract.approval_required_for:
            return await self._request_approval(
                tool, parameters, calling_agent, reason="agent_contract_requires"
            )

        # Check 5: External rate limiting
        if tool.safety_level == SafetyLevel.EXTERNAL:
            if await self._exceeds_external_rate(tool_name):
                return await self._request_approval(
                    tool, parameters, calling_agent, reason="rate_limit_exceeded"
                )

        # Auto-approve
        return SafetyDecision(
            approved=True,
            reason="auto_approved",
            audit_level=tool.audit_logging,
        )

    def _block(
        self, tool: ToolMetadata, agent: str, reason: str
    ) -> SafetyDecision:
        self.audit_log.log(
            event="safety.blocked",
            tool=tool.name,
            agent=agent,
            reason=reason,
        )
        return SafetyDecision(approved=False, reason=reason)

    async def _request_approval(
        self,
        tool: ToolMetadata,
        parameters: dict,
        agent: str,
        reason: str,
    ) -> SafetyDecision:
        self.audit_log.log(
            event="safety.approval_requested",
            tool=tool.name,
            agent=agent,
            reason=reason,
        )

        # Notify operator
        await send_telegram(
            message=f"⚠️ Approval required\n"
                    f"Agent: {agent}\n"
                    f"Tool: {tool.name}\n"
                    f"Reason: {reason}\n"
                    f"Parameters: {parameters}\n\n"
                    f"Reply APPROVE or DENY within 5 minutes."
        )

        approved = await self.approval_service.wait_for_decision(
            timeout=self.config.approval_timeout_seconds
        )

        self.audit_log.log(
            event="safety.approval_resolved",
            tool=tool.name,
            agent=agent,
            approved=approved,
        )

        return SafetyDecision(
            approved=approved,
            reason="human_approved" if approved else "human_denied"
        )
```

---

## 6.5 Audit Log Schema

All safety decisions produce an audit log entry regardless of outcome:

```sql
CREATE TABLE safety_audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    event_type    TEXT NOT NULL,    -- safety.blocked | approval_requested | approved | denied
    tool_name     TEXT NOT NULL,
    calling_agent TEXT NOT NULL,
    reason        TEXT NOT NULL,
    parameters    TEXT,            -- JSON of parameters (sensitive values redacted)
    approved      INTEGER,         -- NULL if not applicable, 0=denied, 1=approved
    decision_by   TEXT,            -- 'auto' or 'human:{telegram_user_id}'
    decision_ms   INTEGER          -- milliseconds to decision
);
```

---

## 6.6 Safety Configuration

```python
class SafetyConfig(BaseModel):
    approval_timeout_seconds: int = 300
    external_rate_limit_per_hour: dict[str, int] = {
        "send_telegram": 50,
        "publish_social": 10,
        "send_email": 20,
    }
    block_on_timeout: bool = True           # Deny if approval not received in time
    audit_all_external: bool = True
    audit_all_critical: bool = True
    notify_on_block: bool = True            # Send Telegram notification on blocked action
```

---

# Part 7 — Memory Access Policy

---

## 7.1 Memory Tiers

The three memory tiers are defined in full in SES-003. This part governs which agents may read, write, summarize, archive, and forget data in each tier.

| Tier | What It Stores | Governed By |
|------|---------------|-------------|
| Working Memory | Current session context (deque, maxlen=20) | Agent-local |
| Episodic Memory | Full interaction log (SQLite) | This policy |
| Semantic Memory | Extracted patterns, vectors (SQLite + Qdrant) | This policy |
| Knowledge Graph | Entity relationships (Neo4j, Phase 4) | SES-003 |

---

## 7.2 Access Matrix

| Operation | Working Memory | Episodic Memory | Semantic Memory | Knowledge Graph |
|-----------|---------------|----------------|----------------|----------------|
| **Read** | All agents | All agents | All agents | All agents |
| **Write (self)** | All agents | All agents | QA Dept only | Engineering Dept only |
| **Write (other agent's data)** | Prohibited | Prohibited | Prohibited | CEO Agent only |
| **Summarize** | All agents | Planning Dept | Planning Dept | — |
| **Archive** | Auto (rolling window) | Planning Dept, CEO | CEO only | — |
| **Forget (delete)** | Auto (rolling window) | CEO Agent only | CEO Agent only | CEO Agent only |

---

## 7.3 Policy Rules

**Rule M-1: Working Memory is agent-local.** An agent may only read and write its own working memory. No agent reads another agent's working memory directly. Cross-agent context passes through events or the Episodic Memory.

**Rule M-2: Episodic Memory is read-all, write-self.** Any agent may read any record in the Episodic Memory. An agent may only write records attributed to itself. Rewriting another agent's episodic record is prohibited.

**Rule M-3: Semantic patterns are written by QA only.** Semantic patterns represent platform-level learned knowledge. Only the QA Department writes new patterns. Other agents propose patterns through the `propose_semantic_pattern` tool — the QA agent evaluates and approves before storage.

**Rule M-4: Forgetting requires CEO approval.** Deleting a memory record is a CRITICAL action (Part 6, L5). It requires CEO Agent approval, which in turn requires operator approval. Memory is not ephemeral — it is the platform's accumulated intelligence.

**Rule M-5: Memory writes must be typed.** No agent writes a raw string to memory. Every write uses a typed data model (`EpisodicEntry`, `SemanticPattern`, `WorkingMemoryEntry`). Untyped memory writes are rejected at the API layer.

---

## 7.4 Memory Access Implementation

```python
class MemoryAccessGate:
    """Enforces memory access policy before any read or write."""

    def check_read(
        self, agent: str, tier: MemoryTier, record_owner: str | None
    ) -> bool:
        # All agents may read all tiers
        return True

    def check_write(
        self, agent: str, tier: MemoryTier, record_owner: str
    ) -> bool:
        if tier == MemoryTier.WORKING:
            # Working memory is local — no cross-agent writes
            return agent == record_owner

        if tier == MemoryTier.EPISODIC:
            return agent == record_owner  # Write only your own records

        if tier == MemoryTier.SEMANTIC:
            # Only QA department agents may write semantic patterns
            return agent in QA_DEPARTMENT_AGENTS

        if tier == MemoryTier.KNOWLEDGE_GRAPH:
            # Only Engineering agents and CEO may write to KG
            return agent in ENGINEERING_DEPARTMENT_AGENTS or agent == "ceo_agent"

        return False

    def check_delete(self, agent: str, tier: MemoryTier) -> bool:
        # Only CEO agent may delete memory (with operator approval via SafetyHarness)
        return agent == "ceo_agent"
```

---

# Part 8 — Agent Communication

---

## 8.1 Communication Surfaces

Agents communicate through four surfaces. The choice depends on the communication pattern:

| Surface | Pattern | When To Use |
|---------|---------|-------------|
| **AgentMessageBus** | Pub/sub events, in-process | Broadcasting state changes within a BMA cycle |
| **Direct API Call** | Request/response, synchronous | One agent needs a result from another immediately |
| **Platform Event Log** | Persistent events, async | Cross-cycle communication, job completion, analytics |
| **Shared Memory** | Read-after-write, indirect | One agent leaves a result; another picks it up later |

---

## 8.2 AgentMessageBus

The in-process message bus for events within a BMA cycle. Every event is typed, every subscriber is registered, every event is traced.

```python
class AgentMessageBus:
    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = {}
        self._history: list[BMAEvent] = []

    def subscribe(self, event_type: str, handler: Callable) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    def publish(self, event: BMAEvent) -> None:
        self._history.append(event)
        opik_trace(event)  # every event is traced
        for handler in self._subscribers.get(event.type, []):
            handler(event)
        for handler in self._subscribers.get("*", []):  # wildcard subscribers
            handler(event)

class BMAEvent(BaseModel):
    type: str                      # dot.notation event type
    agent: str                     # emitting agent name
    cycle_id: str                  # UUID for the current BMA cycle
    timestamp: datetime
    payload: dict
    session_id: str | None = None
```

---

## 8.3 Direct API Calls Between Agents

When an agent needs a synchronous result from another agent, it calls the platform API. Agents do not import each other's Python modules.

```python
# Correct: agent-to-agent via API
async def delegate_to_research(query: str) -> ResearchResult:
    response = await platform_client.post(
        "/api/v1/research/web",
        json={"query": query, "max_results": 5},
        headers={"X-SaathiAI-Token": SAATHI_TOKEN},
    )
    return ResearchResult(**response.json()["data"])

# Violation: direct import of another agent's internals
from app.agents.sub_agents.research import web_search  # PROHIBITED
```

---

## 8.4 Cross-Agent Event Types

Events that cross department boundaries are defined here as typed constants:

```python
class CrossAgentEvents:
    # Planning → All
    TASK_ASSIGNED        = "task.assigned"
    WORKFLOW_STARTED     = "workflow.started"
    WORKFLOW_COMPLETE    = "workflow.complete"
    WORKFLOW_FAILED      = "workflow.failed"

    # Studio → All
    CONTENT_GENERATED    = "content.generated"
    VIDEO_RENDERED       = "video.rendered"
    CONTENT_PUBLISHED    = "content.published"

    # Research → All
    RESEARCH_COMPLETE    = "research.complete"
    SIGNAL_TRIGGERED     = "signal.triggered"

    # QA → All
    EVALUATION_COMPLETE  = "evaluation.complete"
    QUALITY_REJECTED     = "quality.rejected"

    # Voice → All
    STT_COMPLETE         = "stt.complete"
    TTS_COMPLETE         = "tts.complete"

    # Mission Control → All
    ALERT_ISSUED         = "alert.issued"
    OPERATOR_COMMAND     = "operator.command"

    # All → Mission Control
    HEALTH_REPORT        = "health.report"
    JOB_COMPLETE         = "job.complete"
    JOB_FAILED           = "job.failed"
```

---

## 8.5 Observability of Communication

Every message on the bus, every API call between agents, and every event written to the platform log is traced:

1. **AgentMessageBus events** → Opik trace (in-process)
2. **Agent-to-agent API calls** → FastAPI request log with `request_id`, duration, status
3. **Platform Event Log entries** → SQLite `platform_events` table, `processed` flag

No agent communication is invisible to Mission Control.

---

# Part 9 — Failure Recovery

---

## 9.1 Philosophy

Failures are not exceptions. In a live multi-agent system running 24 hours a day, calling external APIs, parsing LLM outputs, and managing schedules — failures are routine operational events.

The failure recovery system in SaathiAI is designed around one principle: **automatic recovery whenever possible; human involvement only when necessary.**

A system that pages the operator for every retry-able API timeout is not autonomous — it is a notification generator. A system that silently ignores failures is ungovernable. The correct path is between those extremes: automatic recovery with full audit trails, and human escalation only for failures that genuinely require human judgment.

---

## 9.2 Failure Classification

| Failure Type | Definition | Default Recovery |
|-------------|-----------|-----------------|
| **Tool Timeout** | Tool did not respond within `timeout_seconds` | Retry up to `max_retries` with backoff |
| **Tool Error** | Tool raised an exception | Retry if `is_retryable=True`, else mark step failed |
| **LLM Failure** | LLM call returned error or empty response | Retry with same model, then with `reasoning` model |
| **LLM Invalid Output** | LLM returned output that fails schema validation | Retry with clarification prompt (up to 2 attempts) |
| **Safety Block** | SafetyHarness blocked an action | Log, notify operator, abort step |
| **Human Rejection** | Operator denied an approval request | Abort step, log reason |
| **Human Timeout** | Approval request timed out | Deny by default (configurable) |
| **Memory Failure** | Memory read/write failed | Proceed with degraded context, log warning |
| **Cycle Limit Exceeded** | `max_cycles` reached without goal completion | Escalate to human with full context |
| **Unrecoverable Tool Failure** | Tool fails after all retries | Mark step `failed`, evaluate if goal still achievable |
| **Dependency Unavailable** | Required service is down (Groq, OmniVoice, etc.) | Route to fallback provider (Part 6.3, SES-001), log |

---

## 9.3 Retry Policy

```python
class RetryPolicy:
    async def execute_with_retry(
        self,
        tool_name: str,
        parameters: dict,
        calling_agent: str,
    ) -> ToolResult:
        tool = TOOL_REGISTRY.get(tool_name)
        max_retries = tool.max_retries if tool.is_retryable else 0
        retry_delays = [2, 10, 60]  # seconds — exponential-ish backoff

        for attempt in range(max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    tool.execute(parameters),
                    timeout=tool.timeout_seconds
                )
                if attempt > 0:
                    logger.info(f"tool.recovered", tool=tool_name, attempt=attempt)
                return result

            except tuple(RETRYABLE_EXCEPTIONS) as e:
                if attempt == max_retries:
                    raise ToolExhaustedError(
                        f"{tool_name} failed after {max_retries} retries"
                    ) from e
                delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                logger.warning(
                    f"tool.retry", tool=tool_name, attempt=attempt + 1, delay=delay
                )
                await asyncio.sleep(delay)

            except FATAL_EXCEPTIONS as e:
                raise ToolFatalError(f"{tool_name} fatal error: {e}") from e
```

---

## 9.4 LLM Failure Recovery

```python
class LLMFailureRecovery:
    async def complete_with_recovery(
        self, prompt: str, model: str, **kwargs
    ) -> LLMResponse:
        try:
            return await llm.complete(prompt, model=model, **kwargs)
        except ProviderUnavailable:
            # Use fallback chain from Model Router
            return await llm.complete(prompt, model=model, force_fallback=True, **kwargs)
        except InvalidResponseError:
            # Retry with reasoning model
            logger.warning("llm.invalid_response", falling_back_to="reasoning")
            return await llm.complete(prompt, model="reasoning", **kwargs)

    async def complete_with_schema_validation(
        self, prompt: str, model: str, schema: type[BaseModel], max_attempts: int = 2
    ) -> BaseModel:
        for attempt in range(max_attempts):
            response = await self.complete_with_recovery(prompt, model)
            try:
                return schema.model_validate_json(response.text)
            except ValidationError as e:
                if attempt == max_attempts - 1:
                    raise LLMOutputInvalid(
                        f"LLM output failed schema validation after {max_attempts} attempts"
                    ) from e
                prompt = RETRY_WITH_CORRECTION_PROMPT.format(
                    original_prompt=prompt,
                    bad_output=response.text,
                    validation_error=str(e),
                )
```

---

## 9.5 Human Escalation Triggers

These conditions automatically escalate to the human operator via Telegram:

```python
HUMAN_ESCALATION_TRIGGERS = {
    "cycle_limit_exceeded": "Agent reached max cycles without completing goal.",
    "all_fallbacks_failed": "All LLM provider fallbacks exhausted.",
    "safety_blocked_critical": "CRITICAL action was blocked by SafetyHarness.",
    "three_consecutive_job_failures": "Scheduled job failed 3 times in a row.",
    "memory_corruption_detected": "Memory consistency check failed.",
    "content_policy_violation": "Content generation triggered a policy violation.",
    "external_rate_limit": "External service rate limit exceeded.",
    "approval_timeout": "Approval request timed out with no response.",
    "unrecoverable_tool_failure": "Tool failed after all retries with fatal error.",
}
```

Escalation message format (Telegram):

```
🚨 SaathiAI Alert
Trigger: {trigger_type}
Agent: {agent_name}
Time: {timestamp}
Context: {context_summary}
Last action: {last_tool_called}

Reply HELP to see recovery options.
Reply ACK to acknowledge.
```

---

## 9.6 Job Failure Policy

For autonomous agents (scheduled jobs), failures have different implications than on-demand failures:

| Consecutive Failures | Action |
|---------------------|--------|
| 1 | Log error, retry at next scheduled time |
| 2 | Log error, increase logging verbosity |
| 3 | Escalate to human via Telegram |
| 5 | Suspend the job, require manual restart |

```sql
-- Job failure tracking
CREATE TABLE scheduler_job_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name        TEXT NOT NULL,
    started_at      DATETIME,
    completed_at    DATETIME,
    status          TEXT NOT NULL,   -- success|failure|suspended
    consecutive_failures INTEGER DEFAULT 0,
    error           TEXT,
    output          TEXT
);
```

---

# Part 10 — Future Multi-Agent Scaling

---

## 10.1 The Scaling Problem

Today, SaathiAI has approximately 20 agents across 8 departments. This is manageable. But the architecture described in this document must support a future where hundreds of specialized agents operate simultaneously — agents for individual IELTS skills, agents for individual content formats, agents for individual markets, agents for individual customers.

If the architecture requires restructuring to add the 50th agent, it will require restructuring to add the 100th. The time to design for scale is when the system is small.

---

## 10.2 Scaling Principles

**P-S1: Agents are registered, not hardcoded.**

No agent name appears in more than two places: the Agent Registry and its own contract file. The CEO agent does not have an `if agent_name == "content_agent"` check. It routes to departments, and departments route internally. Adding a new agent requires only: write the contract, register it, implement it. No other code changes.

**P-S2: Departments are the routing boundary.**

The CEO agent knows departments. Departments know sub-agents. The CEO never needs to know sub-agents. This means adding the 50th studio sub-agent requires no change to the CEO.

**P-S3: Tools are the unit of capability, not agents.**

When a new capability is needed, the first question is "does a tool exist for this?" If yes, any agent can use it immediately. If no, add a tool to the registry. Adding a tool requires no agent changes. Only if the capability requires multi-step reasoning does it become an agent.

**P-S4: The BMA loop is the agent.**

Every agent is the BMA loop with a different contract and toolset. There is no agent-specific loop logic. This means 800 agents use the same loop. The only unique thing about each agent is its contract and its prompts.

**P-S5: Memory scales independently of agents.**

Memory is a platform service, not an agent. Whether there are 20 agents or 2,000, the memory system is the same. An agent stores to episodic memory; another agent reads from it. The memory architecture (SES-003) scales horizontally.

---

## 10.3 The Agent Registry

Every agent is registered in `app/agents/registry.py`. The registry is not a database — it is a typed dictionary at startup. It is the central source of truth for "what agents exist."

```python
AGENT_REGISTRY: dict[str, AgentContract] = {
    "ceo_agent":         ceo_agent.CONTRACT,
    "planner_agent":     planner_agent.CONTRACT,
    "research_director": research_director.CONTRACT,
    "web_search_agent":  web_search_agent.CONTRACT,
    "content_agent":     content_agent.CONTRACT,
    # Adding a new agent: one line here + contract file + implementation
}
```

---

## 10.4 Department Director Protocol

Every department director implements the same interface:

```python
class DepartmentDirector(ABC):
    @abstractmethod
    async def route(self, task: AgentTask) -> AgentTask:
        """Route the task to the appropriate sub-agent."""
        ...

    @abstractmethod
    async def collect(self, results: list[AgentResult]) -> DepartmentResult:
        """Aggregate sub-agent results into a department-level result."""
        ...
```

Adding a new department requires: implement `DepartmentDirector`, register sub-agents, add department to `DepartmentName` enum. The CEO agent and the BMA loop require no changes.

---

## 10.5 Parallel Agent Execution (Phase 3)

Today, agents execute sequentially within a workflow. Phase 3 introduces a parallel execution model for independent workflow steps:

```python
class ParallelWorkflowExecutor:
    async def execute_parallel(
        self, steps: list[ExecutionStep]
    ) -> list[ExecuteResult]:
        # Group steps that have no dependency on each other
        independent_groups = self._group_independent_steps(steps)

        results = []
        for group in independent_groups:
            # Execute independent steps in parallel
            group_results = await asyncio.gather(
                *[self._execute_step(step) for step in group],
                return_exceptions=True
            )
            results.extend(group_results)

        return results
```

The dependency graph between steps is declared in the workflow specification, not in the executor. The executor is dependency-blind — it receives groups.

---

## 10.6 Scaling to Production

When SaathiAI scales to a multi-server deployment (Phase 5), the following architectural decisions, already made, ensure the agent system scales with it:

| Decision | Why It Scales |
|----------|--------------|
| Agent-to-agent via API, not imports | Agents can run on different servers |
| AgentMessageBus events persisted to SQLite | Survives server restart; upgradeable to Redis Streams |
| Tool Registry is a central dictionary | Becomes a service registry with dynamic registration |
| Department Director pattern | Enables department-level horizontal scaling |
| BMA loop is pure Python, no global state | Multiple instances run the same loop concurrently |

---

# Appendix A — Agent Capability Matrix

---

## A.1 Purpose

The Agent Capability Matrix is the single reference for permissions, responsibilities, and governance across all agents. It answers the question "what is Agent X allowed to do?" in one table, without reading every individual contract.

This matrix is generated from the Agent Registry. It is not hand-maintained.

---

## A.2 Primary Capability Matrix

| Capability | CEO | Planner | Research | Engineering | Studio | Voice | QA | Mission Ctrl |
|------------|:---:|:-------:|:--------:|:-----------:|:------:|:-----:|:--:|:------------:|
| **Read Memory (all tiers)** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Write Episodic Memory** | ✓ (own) | ✓ (own) | ✓ (own) | ✓ (own) | ✓ (own) | ✓ (own) | ✓ (own) | ✓ (own) |
| **Write Semantic Patterns** | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ |
| **Delete Memory** | ✓ + Approval | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| **Execute Read Tools (L1)** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Execute Write Tools (L2)** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Execute Modify Tools (L3)** | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ | ✓ | ✓ |
| **Execute External Tools (L4)** | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ |
| **Execute Critical Tools (L5)** | ✓ + Approval | ✗ | ✗ | ✓ + Approval | ✗ | ✗ | ✗ | ✗ |
| **Deploy Code** | ✓ + Approval | ✗ | ✗ | ✓ + Approval | ✗ | ✗ | ✗ | ✗ |
| **Publish Content** | Approve | Draft | Research | ✗ | Create | ✗ | Review | ✗ |
| **Send Telegram** | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ |
| **Approve Other Agents** | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ |
| **Create Scheduled Jobs** | ✓ | ✓ | ✗ | ✓ | ✓ | ✗ | ✗ | ✓ |
| **Cancel Scheduled Jobs** | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ | ✗ | ✓ |
| **Access Production DB** | ✗ | ✗ | ✗ | ✓ + Approval | ✗ | ✗ | ✗ | ✗ |
| **Voice Clone Operations** | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ |
| **Register New Tools** | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ | ✓ | ✗ |
| **Override Safety Rules** | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |

**Legend:** ✓ = Permitted | ✗ = Denied | + Approval = Permitted with explicit human approval | Role label = permitted in that role only

---

## A.3 Tool Category Access by Department

| Tool Category | CEO | Planner | Research | Engineering | Studio | Voice | QA | Mission Ctrl |
|--------------|:---:|:-------:|:--------:|:-----------:|:------:|:-----:|:--:|:------------:|
| `research/*` | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ |
| `communication/*` | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ |
| `content/*` | ✓ | ✓ | ✓ | ✗ | ✓ | ✗ | ✓ | ✗ |
| `data/*` | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ |
| `system/*` | ✓ | ✓ | ✗ | ✓ | ✗ | ✗ | ✗ | ✓ |
| `voice/*` | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ |

---

## A.4 KPI Summary by Department

| Department | Primary KPI | Target | Measurement |
|------------|------------|--------|-------------|
| CEO | Strategic goal completion rate | 90% | Monthly |
| Planning | Workflow success rate | 95% | Weekly |
| Research | Research relevance score | 0.8/1.0 | Per task |
| Engineering | Code execution success rate | 99% | Daily |
| Studio | Content quality score | 0.8/1.0 | Per piece |
| Voice | STT accuracy | 95% | Per session |
| QA | Evaluation accuracy vs. human baseline | 90% | Monthly |
| Mission Control | Alert response time | < 5 min | Per alert |

---

# Acceptance Criteria

| # | Criterion | Verification Method | Priority |
|---|-----------|---------------------|----------|
| AC-001 | Every agent has a completed `AgentContract` and passes `validate_contract()` | Run `python -m app.agents.validate_all_contracts` | Must Have |
| AC-002 | Every tool has a `ToolMetadata` entry in the Tool Registry | Run `python -m app.tools.validate_registry` | Must Have |
| AC-003 | The BMA loop emits all 16 cycle events defined in Part 2.3 | Integration test: run a complete cycle and verify event log | Must Have |
| AC-004 | SafetyHarness blocks a CRITICAL tool call without explicit approval | Unit test: attempt `deploy_to_production` without pre-approval | Must Have |
| AC-005 | Agent Capability Matrix matches the Tool Registry's `allowed_agents` field | Run matrix validation script | Should Have |
| AC-006 | No agent module directly imports another agent's module | `grep -r "from app.agents" app/agents/ --include="*.py" \| grep -v "registry\|bus\|bma\|__init__"` | Must Have |
| AC-007 | Every scheduled job has a `max_consecutive_failures` suspension policy | Code review of all `jobs/*.py` files | Must Have |
| AC-008 | Memory write operations are rejected if the writing agent does not match the record owner (for Episodic) | Unit test: attempt cross-agent Episodic write | Must Have |

---

# Implementation Checklist

**Phase 1 — Core Agent Infrastructure**
- [ ] Implement `app/agents/bus.py` — AgentMessageBus with all 16 event types
- [ ] Implement `app/agents/bma.py` — Full 9-phase BMA loop
- [ ] Implement `app/agents/registry.py` — AGENT_REGISTRY dict with all contracts
- [ ] Implement `app/agents/safety.py` — SafetyHarness with 5-level classification
- [ ] Implement `app/tools/registry.py` — TOOL_REGISTRY with all tool metadata
- [ ] Implement `app/memory/working.py` — deque(maxlen=20) working memory
- [ ] Implement `app/memory/episodic.py` — SQLite episodic memory with gate
- [ ] Write `validate_contract()` function and run against all contracts
- [ ] Write `AgentContract` for: CEO, Planner, Research Director, content_agent, evaluator_agent
- [ ] Write unit tests for BMA loop phases (mock tools, mock LLM)

**Phase 1.5 — Department Directors**
- [ ] Implement `app/agents/orchestrator.py` — top-level routing to departments
- [ ] Implement Department Director for: Studio, Research, QA, Mission Control
- [ ] Implement director routing logic with BMA cycle integration
- [ ] Write integration test: full workflow from trigger to memory update

**Phase 2 — Advanced Features**
- [ ] Implement `MemoryAccessGate` — enforce read/write/delete policy
- [ ] Implement `RetryPolicy` with backoff
- [ ] Implement human approval via Telegram (`ApprovalService`)
- [ ] Implement parallel workflow executor
- [ ] Implement Knowledge Graph interface (stubs for Neo4j, Phase 4)

---

# Risks

| # | Risk | Probability | Impact | Mitigation |
|---|------|-------------|--------|------------|
| R-001 | Agent contracts become stale as implementation evolves | High | Medium | Run contract validation in CI; contract changes require version bump |
| R-002 | SafetyHarness becomes a bottleneck for high-frequency agent operations | Medium | High | Cache safety decisions for read-only tools; only route new decisions through harness |
| R-003 | BMA loop depth becomes unbounded (agent spawns agent spawns agent) | Low | High | Max recursion depth of 3 department calls per cycle; enforced by orchestrator |
| R-004 | Memory growth becomes unmanageable as episodic log grows | Medium | Medium | Implement episodic archival job (weekly, moves records > 90 days to cold storage) |

---

# Dependencies

**Internal:** SES-000C (Architecture Principles), SES-001 (Architecture — folder structure and service definitions), SES-000F (Capability Registry — CAP-XXX IDs referenced in contracts)

**External:**

| Dependency | Purpose | Phase |
|------------|---------|-------|
| APScheduler | Autonomous agent scheduling | 1 |
| python-telegram-bot | Human approval via Telegram, operator alerts | 1 |
| aiosqlite | Episodic and semantic memory storage | 1 |
| opik | BMA cycle tracing, tool invocation tracing | 1 |
| qdrant-client | Semantic memory vector search | 4 |
| neo4j | Knowledge graph for entity relationships | 4 |

---

# Open Questions

| # | Question | Owner | Target | Status |
|---|----------|-------|--------|--------|
| OQ-001 | Should the CEO Agent be implemented as a BMA loop itself, or as a lightweight router that never runs a full cycle? A full CEO BMA cycle adds latency to every workflow. | Ajay | 2026-08-01 | Open |
| OQ-002 | Should `propose_semantic_pattern` (written by all agents, approved by QA) be synchronous or asynchronous? Async means QA runs in a background job; sync means it blocks the LEARN phase. | Ajay | 2026-08-01 | Open |
| OQ-003 | When Phase 3 introduces parallel workflow execution, should the AgentMessageBus remain in-process or move to Redis Pub/Sub for cross-process event delivery? | Ajay | 2026-09-01 | Open |

---

# Related Documents

| Document ID | Title | Relationship |
|-------------|-------|-------------|
| SES-001 | Architecture | Folder structure (`app/agents/`), service registry, event architecture |
| SES-003 | Memory & Knowledge Graph | Memory tiers referenced in Part 7; full specification |
| SES-000F | Capability Registry | CAP-XXX IDs used in agent contracts |
| SES-000C | Architecture Principles | AP-01 through AP-10 all apply to agent design |
| SES-009 | Mission Control | The consumer of all agent events defined in Part 8 |

---

*End of SES-002 Agent System — Version 1.0.0*

*Status: Approved (L3)*

*Next: [`SES-003_MEMORY.md`](SES-003_MEMORY.md)*
