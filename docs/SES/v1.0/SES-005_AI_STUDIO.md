```
================================================================================
SaathiAI Engineering Specification (SES)
================================================================================
Document Title      : AI Studio — Autonomous Content Production System
Document ID         : SES-005
Version             : 1.0.0
Status              : Draft pending review
Maturity            : L1
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
| 1.0.0 | 2026-07-02 | Ajay Chaulagain | Draft — 16-part AI Studio specification with AI Director, Renderer Registry, and Real-Time Studio |

---

## Why This Document Exists

Content is the product. Mr. Yeti is not a mascot bolted onto a marketing plan — Mr. Yeti's videos are the primary vehicle through which pielts reaches students, and the primary surface through which SaathiAI's brand exists in the world. A platform that can reason, remember, and speak (SES-002, SES-003, SES-004) but cannot autonomously produce finished video content has an operating system with no application running on top of it.

AI Studio is that application. It is SaathiAI's autonomous content production department — the system that takes a single instruction and carries it, without human intervention for routine work, through research, scripting, direction, storyboarding, character rendering, voice synthesis, video rendering, quality assurance, and publishing.

This document exists because content production, done manually, does not scale. One person cannot research, script, direct, animate, voice, edit, and publish a daily video across three platforms while also running a canteen and building a platform. AI Studio exists to make daily, high-quality Mr. Yeti content production possible without consuming Ajay's time on anything but strategic direction and occasional creative review.

AI Studio depends on and extends two other SES documents directly:

- **SES-002 Agent System** — every department in AI Studio is built from agents that follow the BMA loop and are governed by the SafetyHarness. Nothing in this document introduces a new agent execution model; it composes SES-002 primitives into a production pipeline.
- **SES-003 Memory** — AI Studio is one of the platform's largest producers and consumers of memory. Every production is an episodic record; every performance pattern is a candidate semantic pattern; the character bible and persona are Knowledge Graph entities.
- **SES-004 Voice OS** — AI Studio does not implement its own text-to-speech or facial-animation pipeline. It calls the Multimodal Interaction Layer that SES-004 defines, exactly as any other product would. The Real-Time Studio chapter (Part 12) is the second production instantiation of the MIL, after Voice OS itself.

The architectural principle governing this document: **AI Studio is a production department, not a video generation script.** It has departments, directors, contracts, state machines, and a self-improvement loop — the same organizational shape as the rest of the platform, applied to the domain of turning ideas into published video.

---

## Audience

| Role | Required Sections | Notes |
|------|------------------|-------|
| All Engineers | Parts 1, 2, 3 | Vision, pipeline architecture, and the Studio Director orchestrator |
| Content/Creative Engineers | Parts 4–10 | Research through Voice departments — the "what to say and how" layers |
| Rendering Engineers | Part 11, Appendix E | Renderer Registry, adapters, adding new rendering backends |
| Real-Time/Voice Engineers | Part 12 | Live avatar streaming, built on SES-004's Multimodal Interaction Layer |
| QA/Publishing Engineers | Parts 13, 14 | Quality gates and cross-platform publishing |
| Product/Strategy | Parts 1, 15, 16, Appendix A | Vision, analytics, self-improvement, Mr. Yeti character spec |
| Finance/Ops | Appendix B | Cost model and per-video budget |

---

## Reading Order

```
SES-002 Agent System (BMA Loop, AgentContract, SafetyHarness)
SES-003 Memory (Episodic/Semantic Memory, Memory Promotion Engine)
SES-004 Voice OS (Multimodal Interaction Layer, OmniVoice TTS, Personas)
        │
        ▼
SES-005 AI Studio  ← You are here
        │
        ├── SES-006 Autonomous Engineering (platform self-improvement, general case)
        ├── SES-007 Mission Control (operator visibility into Studio productions)
        └── SES-010 Discovery Engine (pre-publish optimization gate)
```

---

## Document Structure

| Part | Title | The Question It Answers |
|------|-------|-------------------------|
| 1 | Vision | What is AI Studio trying to be? What does "zero human intervention" mean in practice? |
| 2 | Architecture | What is the full production pipeline, and what state machine governs it? |
| 3 | Studio Director | Who orchestrates the whole production? |
| 4 | Research Department | Where does source material come from? |
| 5 | Script Department | What gets said, and how is it timed? |
| 6 | AI Director | How is the story told — pacing, camera, retention design? |
| 7 | Storyboard Engine | What does each scene concretely look like? |
| 8 | Character Department | How does Mr. Yeti stay visually consistent? |
| 9 | Asset Department | How are reusable assets managed and stored? |
| 10 | Voice Department | How does narration get generated, without duplicating Voice OS? |
| 11 | Rendering Department | How are scenes turned into video, across multiple swappable renderers? |
| 12 | Real-Time Studio | How does Mr. Yeti appear live, with sub-200ms lip sync? |
| 13 | QA Department | What quality gates must a production pass before publishing? |
| 14 | Publishing Department | How does content reach YouTube, TikTok, Instagram, Facebook? |
| 15 | Analytics Department | How is performance tracked and fed back into memory? |
| 16 | Self-Improvement Loop | How does the Studio get better over time? |
| Appendix A | Mr. Yeti Full Production Spec | Character bible and a full brief-to-published walkthrough |
| Appendix B | Cost Model | Per-production cost breakdown and target budget |
| Appendix C | Pipeline Examples | Three fully worked productions of increasing complexity |
| Appendix D | Failure Recovery | Retry policy, fallback renderers, resumable state machine |
| Appendix E | Future Rendering Engines | How to add a new renderer with zero other code changes |

---

# Part 1 — Vision

---

## 1.1 The Problem AI Studio Solves

A single instruction — "make an IELTS tip video about paraphrasing" — implies a dozen decisions that a human content creator makes almost unconsciously: What does the audience already know? What tone fits this platform? How long should it run? What's the hook? What does Mr. Yeti do with his hands while he explains this? What music plays under the explanation? What text appears on screen when he says "synonym"? Where does this get published, and when?

Without AI Studio, each of these decisions requires either a human in the loop for every single video, or a rigid template that produces repetitive, low-quality content. Neither scales to the volume SaathiAI's content strategy requires: daily Mr. Yeti content across YouTube Shorts, TikTok, and Instagram, sustained over months, without degrading in quality or consistency.

AI Studio exists to be SaathiAI's autonomous content production department — a system that takes the single instruction and autonomously carries it through the full production chain: research, scripting, direction, storyboarding, character rendering, voice, video rendering, quality assurance, and publishing, arriving at a published, on-brand video with zero human intervention for routine content.

---

## 1.2 The Mr. Yeti Use Case

Mr. Yeti is SaathiAI's flagship content character: a warm, funny, slightly eccentric IELTS teacher in yeti form, built to make Nepali and international students feel like learning English for the exam is approachable rather than intimidating. Mr. Yeti is the primary content vehicle for the pielts product and, over time, for SaathiAI's brand as a whole.

Every part of this document is grounded in producing Mr. Yeti content, because that is the concrete, shipping use case AI Studio is built to serve first. The pipeline is general — a future product could bring its own character and voice persona through the same departments — but the acceptance bar for every department in this document is: **does this produce a Mr. Yeti IELTS Shorts video that is good enough to publish without a human watching it first?**

Target output formats: YouTube Shorts (9:16, ≤60s), TikTok (9:16, ≤60s), Instagram Reels (9:16, ≤90s), with longer-form YouTube explainers (16:9, 3–8 minutes) as a secondary format once the short-form pipeline is proven.

---

## 1.3 Zero Human Intervention, With Gates

"Zero human intervention" does not mean "no human ever looks at anything." It means the default path for routine content requires no human action. Human involvement is reserved for two categories:

**High-stakes content.** Anything that makes a factual claim about IELTS scoring criteria, cites a statistic, or could be interpreted as legal, medical, or financial advice is routed to a human approval gate before publishing, regardless of how well it scores on automated QA (Part 13).

**Novel content.** The first video in a new format, the first video addressing a new topic area, or any production where the AI Director (Part 6) reports low confidence in its own beat sheet, is routed to a human review gate. Once a format or topic has produced three or more approved productions, it graduates to the routine path.

This mirrors the SafetyHarness's approval model in SES-002: the system does not ask permission for every action, but it knows which actions are consequential enough to require it, and it escalates deterministically rather than by chance.

---

## 1.4 What "Department" Means Here

AI Studio is organized as a set of departments, matching the organizational model established in SES-002 Part 6: each department owns a domain of the production pipeline, has a director-equivalent agent (in most cases a single specialized agent; in Rendering, a registry of adapters), and communicates with adjacent departments through defined input/output contracts rather than ad hoc function calls. This gives AI Studio the same property the rest of the platform has: when a new capability is needed, "which department owns this?" has a deterministic answer.

---

# Part 2 — Architecture

---

## 2.1 The Production Pipeline

AI Studio is a directed flow of departments. Each department consumes the previous department's output and produces a well-defined artifact for the next. The flow is not strictly linear in implementation (QA can send a production back to an earlier department; the Self-Improvement Loop feeds forward into future productions rather than the current one), but the primary path is a pipeline.

```
                          ┌─────────────────────┐
                          │   STUDIO DIRECTOR    │◄────────────────┐
                          │  (LangGraph          │                 │
                          │   StateGraph)        │                 │
                          └──────────┬───────────┘                 │
                                     │ brief                       │
                                     ▼                             │
                          ┌─────────────────────┐                  │
                          │ RESEARCH DEPARTMENT  │                  │
                          └──────────┬───────────┘                  │
                                     │ research_brief               │
                                     ▼                             │
                          ┌─────────────────────┐                  │
                          │  SCRIPT DEPARTMENT   │  (what to say)   │
                          └──────────┬───────────┘                  │
                                     │ script                       │
                                     ▼                             │
                          ┌─────────────────────┐                  │
                          │    AI DIRECTOR       │  (how to tell it)│
                          └──────────┬───────────┘                  │
                                     │ beat_sheet                   │
                                     ▼                             │
                          ┌─────────────────────┐                  │
                          │ STORYBOARD ENGINE    │  (scene specs)   │
                          └──────────┬───────────┘                  │
                                     │ storyboard                   │
                     ┌───────────────┼────────────────┐            │
                     ▼               ▼                ▼            │
          ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
          │  CHARACTER   │ │    ASSET     │ │    VOICE     │       │
          │  DEPARTMENT  │ │  DEPARTMENT  │ │  DEPARTMENT  │       │
          └──────┬───────┘ └──────┬───────┘ └──────┬───────┘       │
                 └────────────────┼────────────────┘                │
                                  ▼                                 │
                       ┌─────────────────────┐                      │
                       │ RENDERING DEPARTMENT │                      │
                       │ (Renderer Registry + │                      │
                       │  FFmpeg assembly)    │                      │
                       └──────────┬───────────┘                      │
                                  │ rendered_video                   │
                                  ▼                                  │
                       ┌─────────────────────┐                      │
                       │   QA DEPARTMENT      │──── fail ───────────►│ (retry earlier stage)
                       └──────────┬───────────┘                      │
                                  │ pass                              │
                                  ▼                                  │
                       ┌─────────────────────┐                      │
                       │ PUBLISHING DEPARTMENT│                      │
                       └──────────┬───────────┘                      │
                                  │ published_content                │
                                  ▼                                  │
                       ┌─────────────────────┐                      │
                       │ ANALYTICS DEPARTMENT │                      │
                       └──────────┬───────────┘                      │
                                  │ performance_data                 │
                                  ▼                                  │
                       ┌─────────────────────┐                      │
                       │ SELF-IMPROVEMENT LOOP├──────────────────────┘
                       │ (feeds Script Dept + │
                       │  AI Director context)│
                       └───────────────────────┘
```

The Character, Asset, and Voice departments run in parallel once the Storyboard Engine has produced its scene specs — they are independent inputs to Rendering and do not depend on each other's output.

---

## 2.2 The Production State Machine

Every production is a single instance of a state machine, tracked by the Studio Director. The state machine is the mechanism by which a production can be paused, resumed, retried, or escalated without losing its place.

```
IDLE
  │  brief received
  ▼
BRIEFED
  │  Research Department dispatched
  ▼
RESEARCHING ──────────────► FAILED ──► RETRYING ──► RESEARCHING
  │  research_brief complete
  ▼
SCRIPTING ────────────────► FAILED ──► RETRYING ──► SCRIPTING
  │  script complete
  ▼
DIRECTING ────────────────► FAILED ──► RETRYING ──► DIRECTING
  │  beat_sheet complete
  ▼
STORYBOARDING ─────────────► FAILED ──► RETRYING ──► STORYBOARDING
  │  storyboard complete
  ▼
IN_PRODUCTION ─────────────► FAILED ──► RETRYING ──► IN_PRODUCTION
  │  (Character + Asset + Voice + Rendering complete)
  ▼
QA ────────────────────────► FAILED ──► RETRYING (resume from failing stage)
  │  pass
  ▼
APPROVED ──── high-stakes/novel? ──► human review gate ──► APPROVED
  │
  ▼
PUBLISHING ────────────────► FAILED ──► RETRYING ──► PUBLISHING
  │  published
  ▼
LIVE
  │  performance window elapsed (default: 7 days)
  ▼
ANALYZING
  │  performance_data written
  ▼
COMPLETE
```

`FAILED` and `RETRYING` are side states attached to every primary state — a production in any primary state can transition to `FAILED` on an unrecoverable department error, and from `FAILED` to `RETRYING`, which re-enters the primary state that failed (see Appendix D for the full retry policy and resumability rules).

---

## 2.3 LangGraph as the Orchestration Mechanism

The Studio Director is implemented as a LangGraph `StateGraph`. LangGraph is chosen over a hand-rolled state machine because production flows have exactly the properties LangGraph is built for: named states, conditional edges (QA pass/fail, high-stakes routing), and a persisted checkpoint after every node so a production can be resumed after a process restart without replaying completed work.

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

class ProductionState(TypedDict):
    production_id: str
    brief: ContentBrief
    state: str                      # current node name / ProductionState enum value
    research_brief: ResearchBrief | None
    script: Script | None
    beat_sheet: DirectorialBeatSheet | None
    storyboard: Storyboard | None
    character_assets: CharacterAssets | None
    scene_assets: SceneAssets | None
    voice_track: VoiceTrack | None
    rendered_clips: list[RenderedClip]
    final_video: RenderedVideo | None
    qa_result: QAResult | None
    requires_human_review: bool
    published: PublishResult | None
    performance: PerformanceReport | None
    retry_count: int
    last_error: str | None


def build_studio_graph() -> StateGraph:
    graph = StateGraph(ProductionState)

    graph.add_node("research", research_node)
    graph.add_node("script", script_node)
    graph.add_node("direct", ai_director_node)
    graph.add_node("storyboard", storyboard_node)
    graph.add_node("produce", production_fanout_node)   # character+asset+voice+render
    graph.add_node("qa", qa_node)
    graph.add_node("human_review", human_review_node)
    graph.add_node("publish", publish_node)
    graph.add_node("analyze", analytics_node)
    graph.add_node("retry", retry_node)

    graph.set_entry_point("research")

    graph.add_conditional_edges("research", route_on_outcome,
        {"success": "script", "failure": "retry"})
    graph.add_conditional_edges("script", route_on_outcome,
        {"success": "direct", "failure": "retry"})
    graph.add_conditional_edges("direct", route_on_outcome,
        {"success": "storyboard", "failure": "retry"})
    graph.add_conditional_edges("storyboard", route_on_outcome,
        {"success": "produce", "failure": "retry"})
    graph.add_conditional_edges("produce", route_on_outcome,
        {"success": "qa", "failure": "retry"})
    graph.add_conditional_edges("qa", route_on_qa,
        {"pass_routine": "publish", "pass_needs_review": "human_review",
         "fail": "retry"})
    graph.add_conditional_edges("human_review", route_on_review,
        {"approved": "publish", "rejected": "retry"})
    graph.add_conditional_edges("publish", route_on_outcome,
        {"success": "analyze", "failure": "retry"})
    graph.add_edge("analyze", END)
    graph.add_conditional_edges("retry", route_retry,
        {"resume": "research", "abandon": END})   # resume target varies by failed stage

    return graph


async def research_node(state: ProductionState) -> ProductionState:
    result = await research_agent.run(brief=state["brief"])
    return {**state, "research_brief": result.output, "state": "RESEARCHING"}


def route_on_outcome(state: ProductionState) -> str:
    return "success" if state.get("last_error") is None else "failure"


def route_on_qa(state: ProductionState) -> str:
    qa = state["qa_result"]
    if not qa.passed:
        return "fail"
    return "pass_needs_review" if state["requires_human_review"] else "pass_routine"


studio_graph = build_studio_graph().compile(
    checkpointer=SqliteSaver.from_conn_string("studio_checkpoints.db")
)
```

The `SqliteSaver` checkpoint means every node transition is durable. If the process crashes mid-production, the Studio Director resumes from the last completed node rather than restarting the entire pipeline — this is the mechanism underlying the partial production recovery described in Appendix D.

---

## 2.4 Department Interface Contract

Every department in this document, without exception, exposes the same shape of interface to the Studio Director: an async `run()` method that accepts a typed input and returns a typed output plus an outcome flag. This uniformity is what lets the Studio Director treat all departments interchangeably in the graph above.

```python
class DepartmentResult(BaseModel, Generic[T]):
    output: T | None
    outcome: Literal["success", "failure", "partial"]
    error: str | None = None
    cost_usd: float = 0.0
    duration_ms: int = 0

class Department(Protocol[TIn, TOut]):
    async def run(self, input: TIn, context: ProductionContext) -> DepartmentResult[TOut]:
        ...
```

`ProductionContext` carries the `production_id`, the assembled memory context (SES-003 Context Assembly Engine), and the cost budget remaining for this production (Part 3.4).

---

# Part 3 — Studio Director

---

## 3.1 Role

The Studio Director is the top-level orchestrator agent for AI Studio. It is the department director in the SES-002 sense — it does not itself research, write, or render anything. It receives briefs, decomposes them into department tasks, drives the LangGraph state machine defined in Part 2, tracks production state, handles failures and retries, and enforces the cost budget for each production.

Briefs arrive from three sources: the future Dream Engine/Mission Control (SES-006/SES-007, scheduled or strategy-driven), a human operator (ad hoc "make a video about X"), or the Self-Improvement Loop proposing a production based on a detected content gap (Part 16).

---

## 3.2 AgentContract: `studio_director`

```python
AgentContract(
    name="studio_director",
    display_name="AI Studio Director",
    version="1.0.0",
    department="ai_studio",
    parent_agent=None,                 # Reports to ceo_agent, not another Studio agent

    purpose="Orchestrate a content brief through the full AI Studio production pipeline to a published video.",
    why_it_exists="Without a single owner of production state, no agent can answer 'where is this video in production' or enforce a cost ceiling across departments.",
    capabilities_owned=["CAP-040"],
    interfaces_exposed=["POST /api/v1/studio/produce", "GET /api/v1/studio/production/{id}"],
    dependents=["mission_control", "dream_engine"],

    inputs=[
        InputSpec(name="brief", type="ContentBrief", required=True),
        InputSpec(name="priority", type="Priority", required=False),
        InputSpec(name="budget_ceiling_usd", type="float", required=False),
    ],
    outputs=[
        OutputSpec(name="production_state", type="ProductionState"),
        OutputSpec(name="published_content", type="PublishResult | None"),
    ],
    tools=[
        "dispatch_research", "dispatch_script", "dispatch_ai_director",
        "dispatch_storyboard", "dispatch_production_fanout", "dispatch_qa",
        "dispatch_publish", "dispatch_analytics", "notify_human_review",
        "search_memory",
    ],

    memory_read=MemoryAccessSpec(working=True, episodic=True, semantic=True),
    memory_write=MemoryAccessSpec(working=True, episodic=True, semantic=False),

    events_published=[
        "studio.production.started", "studio.production.state_changed",
        "studio.production.failed", "studio.production.completed",
    ],
    events_consumed=["content.brief.created", "scheduler.daily_content_slot"],

    safety_level=SafetyLevel.WRITE,       # publishing itself is gated separately (Part 14)
    approval_required_for=["budget_ceiling_override"],
    human_escalation_triggers=[
        "three_consecutive_department_failures",
        "cost_budget_exceeded_80_percent",
        "novel_content_flagged_by_ai_director",
        "high_stakes_content_detected",
    ],

    failure_policy=FailurePolicy(
        tool_failure="retry_with_backoff_max_3",
        llm_failure="retry_with_reasoning_model",
        timeout="mark_failed_and_escalate",
        invalid_output="retry_with_clarification",
    ),
    max_cycles=20,

    kpis=[
        KPISpec(metric="production_success_rate", target=0.95, unit="rate_0_to_1"),
        KPISpec(metric="time_to_publish_minutes", target=45, unit="minutes"),
        KPISpec(metric="cost_per_production_usd", target=2.50, unit="usd"),
    ],
    sla_seconds=None,   # productions are minutes-scale, not real-time
)
```

---

## 3.3 Responsibilities

**Brief intake and decomposition.** A `ContentBrief` is intentionally thin — a topic, a target platform set, and optionally a tone override. The Studio Director does not decompose the brief into scenes itself; it hands the brief to Research, then Script, then the AI Director, each of which adds a layer of specificity. The Director's decomposition job is at the department level, not the content level.

```python
class ContentBrief(BaseModel):
    brief_id: str
    topic: str                          # "paraphrasing techniques for IELTS Writing Task 2"
    character: str = "mr_yeti"
    target_platforms: list[str]         # ["youtube_shorts", "tiktok", "instagram_reels"]
    tone_override: str | None = None
    requested_by: str                   # "dream_engine" | "operator" | "self_improvement_loop"
    priority: Priority = Priority.NORMAL
    budget_ceiling_usd: float = 3.00
    created_at: datetime
```

**State tracking.** Every state transition in the Production State Machine (Part 2.2) is written to the `productions` table and emitted as a `studio.production.state_changed` event, so Mission Control (SES-007) can render live production status without polling.

```sql
CREATE TABLE productions (
    production_id   TEXT PRIMARY KEY,
    brief_json      TEXT NOT NULL,
    state           TEXT NOT NULL,       -- matches ProductionState enum
    retry_count     INTEGER DEFAULT 0,
    cost_so_far_usd REAL DEFAULT 0.0,
    budget_ceiling_usd REAL NOT NULL,
    requires_human_review INTEGER DEFAULT 0,
    started_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at    DATETIME,
    last_error      TEXT
);
CREATE INDEX idx_productions_state ON productions(state);
```

**Failure and retry handling.** Delegated to the `retry` node in the state graph (Part 2.3) and specified fully in Appendix D. The Director's role is to decide *whether* to retry (bounded by `max_cycles` and the cost ceiling) and *where* to resume — it does not re-run departments that already succeeded.

**Budget enforcement.** Every department call returns a `cost_usd` on its `DepartmentResult`. The Studio Director accumulates this against `budget_ceiling_usd` and halts the production — routing to human escalation rather than silently overspending — the moment projected total cost would exceed the ceiling by more than 20%.

---

## 3.4 Cost Budget Enforcement

```python
class BudgetGuard:
    OVERRUN_TOLERANCE = 1.20

    async def check(
        self, production_id: str, department_cost: float
    ) -> BudgetDecision:
        production = await db.get_production(production_id)
        new_total = production.cost_so_far_usd + department_cost

        if new_total > production.budget_ceiling_usd * self.OVERRUN_TOLERANCE:
            await db.update_production(production_id, state="FAILED",
                last_error="budget_ceiling_exceeded")
            await notify_human_review(
                production_id=production_id,
                reason=f"Cost ${new_total:.2f} exceeds ceiling ${production.budget_ceiling_usd:.2f}",
            )
            return BudgetDecision(allow=False, escalate=True)

        await db.update_production(production_id, cost_so_far_usd=new_total)
        return BudgetDecision(allow=True, escalate=False)
```

---

# Part 4 — Research Department

---

## 4.1 Role

The Research Department gathers the source material a script will be built from. For Mr. Yeti IELTS content, this means IELTS band descriptors and examiner criteria, trending topics among IELTS candidates (what students are actually confused about, sourced from forums and search trends), competitor content analysis (what other IELTS YouTubers/TikTokers have already covered, and how), and fact-checking of any specific claim the brief implies.

Research does not write anything narrative. Its output is a structured brief of facts, angles, and evidence — raw material the Script Department will shape into a script.

---

## 4.2 AgentContract: `research_agent`

```python
AgentContract(
    name="research_agent",
    display_name="Studio Research Agent",
    version="1.0.0",
    department="ai_studio",
    parent_agent="studio_director",

    purpose="Gather verified source material and content angles for a given content brief.",
    why_it_exists="Scripts written without grounded research repeat generic advice or make unverified claims; a dedicated research step keeps content accurate and differentiated.",
    capabilities_owned=["CAP-041"],
    interfaces_exposed=["internal:studio.research"],
    dependents=["script_agent"],

    inputs=[
        InputSpec(name="brief", type="ContentBrief", required=True),
    ],
    outputs=[
        OutputSpec(name="research_brief", type="ResearchBrief"),
    ],
    tools=[
        "research_web", "search_memory", "query_knowledge_graph",
        "fetch_ielts_band_descriptors", "analyze_competitor_content",
    ],

    memory_read=MemoryAccessSpec(working=True, episodic=True, semantic=True),
    memory_write=MemoryAccessSpec(working=True, episodic=True, semantic=False),

    events_published=["studio.research.completed", "studio.research.failed"],
    events_consumed=[],

    safety_level=SafetyLevel.READ,
    approval_required_for=[],
    human_escalation_triggers=["fact_check_confidence_below_threshold"],

    failure_policy=FailurePolicy(
        tool_failure="retry_once_then_skip",
        llm_failure="retry_with_reasoning_model",
        timeout="abort_and_log",
        invalid_output="retry_with_clarification",
    ),
    max_cycles=5,

    kpis=[
        KPISpec(metric="fact_check_pass_rate", target=0.98, unit="rate_0_to_1"),
        KPISpec(metric="research_latency_ms", target=8000, unit="ms"),
    ],
    sla_seconds=15,
)
```

---

## 4.3 What Research Gathers

| Category | Source | Example |
|----------|--------|---------|
| IELTS band descriptors | Cached British Council / IDP public rubric text, refreshed quarterly | "Band 7 Lexical Resource requires flexible use of vocabulary to discuss variety of topics" |
| Trending topics | `research_web` against IELTS forums, Reddit r/IELTS, search trend snapshots | "Candidates frequently ask how to paraphrase question prompts without changing meaning" |
| Competitor content analysis | `analyze_competitor_content` against known IELTS YouTube/TikTok channels | "Most competitor paraphrasing videos give 3 generic synonyms; none demonstrate sentence-level restructuring" |
| Fact-checking | Cross-reference claim against Knowledge Graph `VerifiedFact` nodes (SES-003 Part 3.2) and, if absent, a `reasoning`-label LLM verification pass | "Claim: 'paraphrasing the whole sentence structure scores higher than synonym swapping' — verified against band descriptor text" |

---

## 4.4 SQLite Schema: `research_briefs`

```sql
CREATE TABLE research_briefs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    production_id       TEXT NOT NULL,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,

    topic               TEXT NOT NULL,
    key_facts           TEXT NOT NULL,      -- JSON array of {fact, source, confidence}
    trending_angles     TEXT,               -- JSON array of {angle, evidence, relevance_score}
    competitor_gaps     TEXT,               -- JSON array of {gap, opportunity}
    fact_check_status   TEXT DEFAULT 'pending',  -- pending|verified|flagged
    fact_check_notes    TEXT,

    is_high_stakes      INTEGER DEFAULT 0,  -- flips human review gate downstream (Part 1.3)
    tool_calls_made     TEXT,               -- JSON array, for audit
    cost_usd            REAL DEFAULT 0.0
);
CREATE INDEX idx_research_production ON research_briefs(production_id);
```

`is_high_stakes` is set to `1` whenever a fact-check pass finds a claim it cannot verify with confidence ≥ 0.85, or the topic matches a configured high-stakes keyword list (scoring methodology, visa/legal implications, health claims). This flag propagates through the pipeline and is the mechanism the Studio Director uses to route to human review at the QA gate (Part 13.4).

---

# Part 5 — Script Department

---

## 5.1 Role

The Script Department converts the research brief and the original content brief into a written script with timing markers. This department decides **what** Mr. Yeti says — the words, their order, and roughly how long each part should take to speak. It does not decide camera angles, pacing beats, or visual composition; that is the AI Director's job (Part 6), operating one layer up in abstraction.

---

## 5.2 AgentContract: `script_agent`

```python
AgentContract(
    name="script_agent",
    display_name="Studio Script Agent",
    version="1.0.0",
    department="ai_studio",
    parent_agent="studio_director",

    purpose="Write a timed narration script from a research brief and content brief.",
    why_it_exists="Separating script writing from directorial and visual decisions keeps each layer independently revisable — a script can be rewritten without redoing the shot plan.",
    capabilities_owned=["CAP-042"],
    interfaces_exposed=["internal:studio.script"],
    dependents=["ai_director_agent"],

    inputs=[
        InputSpec(name="brief", type="ContentBrief", required=True),
        InputSpec(name="research_brief", type="ResearchBrief", required=True),
    ],
    outputs=[
        OutputSpec(name="script", type="Script"),
    ],
    tools=["generate_content", "get_persona_profile", "search_memory"],

    memory_read=MemoryAccessSpec(working=True, episodic=True, semantic=True),
    memory_write=MemoryAccessSpec(working=True, episodic=True, semantic=False),

    events_published=["studio.script.completed", "studio.script.failed"],
    events_consumed=[],

    safety_level=SafetyLevel.WRITE,
    approval_required_for=[],
    human_escalation_triggers=["content_policy_violation_detected"],

    failure_policy=FailurePolicy(
        tool_failure="retry_once_then_skip",
        llm_failure="retry_with_reasoning_model",
        timeout="abort_and_log",
        invalid_output="retry_with_clarification",
    ),
    max_cycles=5,

    kpis=[
        KPISpec(metric="script_word_count_accuracy", target=0.9, unit="rate_0_to_1"),
        KPISpec(metric="script_revision_rate", target=0.1, unit="rate_0_to_1"),
    ],
    sla_seconds=10,
)
```

---

## 5.3 Script Schema

```json
{
  "script_id": "scr_9a21",
  "production_id": "prod_7f3e",
  "character": "mr_yeti",
  "target_duration_seconds": 42,
  "segments": [
    {
      "segment_id": "seg_1",
      "role": "hook",
      "text": "Think swapping one word makes a good paraphrase? Big mistake.",
      "start_seconds": 0.0,
      "end_seconds": 3.2,
      "tone_marker": "playful_challenge"
    },
    {
      "segment_id": "seg_2",
      "role": "setup",
      "text": "Paraphrasing isn't a synonym swap. It's rebuilding the sentence.",
      "start_seconds": 3.2,
      "end_seconds": 7.0,
      "tone_marker": "explain"
    },
    {
      "segment_id": "seg_3",
      "role": "example",
      "text": "Instead of 'many people think', try 'it is widely believed that'.",
      "start_seconds": 7.0,
      "end_seconds": 12.5,
      "tone_marker": "example"
    },
    {
      "segment_id": "seg_4",
      "role": "cta",
      "text": "Practice this on your next Task 2 prompt. Follow for more.",
      "start_seconds": 38.0,
      "end_seconds": 42.0,
      "tone_marker": "encourage"
    }
  ],
  "word_count": 96,
  "reading_pace_wpm": 137,
  "fact_check_refs": ["research_briefs.id=1042"]
}
```

`tone_marker` values map directly to the `registers` defined in the `mr_yeti` `VoicePersona` in SES-004 Part 5.2 (`default`, `encourage`, `correct`, `celebrate`, `explain`) — the Script Department writes in the vocabulary the Voice Department already understands, avoiding a translation step later.

---

# Part 6 — AI Director

---

## 6.1 Why a New Department Sits Between Script and Storyboard

A script tells you what Mr. Yeti says. It does not tell you how the story is told. Two productions can share the identical script and be completely different videos: one holds on a static shot with text overlays; the other cuts between three camera angles, builds tension before the punchline, and times a zoom to land exactly on the word "mistake." The difference is direction — a distinct creative and technical skill from writing.

Before this department existed (see Brain.md Section 8, "AI Director above Storyboard"), the Storyboard Engine had to infer pacing, retention design, and platform adaptation on its own, conflating "what does this scene look like" with "why does this scene exist and how long should it last." Those are different questions, and conflating them made both the storyboard and the pacing worse. Separating them means each layer can be independently improved: the AI Director's beat sheets can get better at retention without anyone touching how a storyboard scene is composed, and vice versa.

The AI Director decides:

- **Pacing** — how much screen time each idea gets, and where the cuts fall
- **Emotional arc** — where in the video Mr. Yeti is playful vs. serious vs. encouraging
- **Audience retention curve design** — where the hook lands, where the mid-video re-hook goes, how attention is re-captured before the platform's typical drop-off point
- **Platform adaptation** — a 9:16 Short is directed differently from a 16:9 explainer, even from the same script
- **Camera style and movement language** — static vs. dynamic, when to push in, when to cut
- **Educational strategy** — for IELTS content specifically, how to teach the underlying concept effectively, not just narrate it
- **Shot-by-shot beat sheet** — the concrete output that the Storyboard Engine consumes

---

## 6.2 Layering: Script → AI Director → Storyboard

```
SCRIPT DEPARTMENT           AI DIRECTOR                  STORYBOARD ENGINE
─────────────────           ───────────                  ──────────────────
"What does Mr. Yeti          "How is this told?"          "What does each scene
 say, and when?"                                           concretely look like?"

Script (text + timing)  ──►  DirectorialBeatSheet    ──►  StoryboardScene[]
                              (pacing, emotion,             (composition, character
                               camera, retention               position/expression,
                               hooks, per-beat                 background, on-screen
                               duration)                       text, asset needs)
```

Each layer adds concreteness. The Script Department answers "what." The AI Director answers "how." The Storyboard Engine answers "exactly what does this look like, frame by frame." No layer skips ahead into the next layer's decisions — the AI Director does not choose backgrounds, and the Storyboard Engine does not re-decide pacing.

---

## 6.3 Model Label

The AI Director uses the `reasoning` LLM label (per SES-002 Part 3.3's model-label conventions, e.g. `model="reasoning"` routed to Claude). Directorial decisions — pacing, retention design, teaching strategy — require the kind of multi-step, weighing-tradeoffs reasoning that a `standard` model handles poorly. This mirrors the routing rule established in SES-002 Part 3 ("complex → reasoning model").

---

## 6.4 AgentContract: `ai_director_agent`

```python
AgentContract(
    name="ai_director_agent",
    display_name="AI Studio Director (Creative)",
    version="1.0.0",
    department="ai_studio",
    parent_agent="studio_director",

    purpose="Translate a script into a directorial beat sheet defining pacing, emotional arc, camera language, and retention design.",
    why_it_exists="Storytelling decisions (how) are a distinct skill from writing (what) and from scene construction (concretely what it looks like); collapsing them into one step produced worse pacing and worse storyboards.",
    capabilities_owned=["CAP-043"],
    interfaces_exposed=["internal:studio.direct"],
    dependents=["storyboard_engine_agent"],

    inputs=[
        InputSpec(name="script", type="Script", required=True),
        InputSpec(name="target_platforms", type="list[str]", required=True),
    ],
    outputs=[
        OutputSpec(name="beat_sheet", type="DirectorialBeatSheet"),
    ],
    tools=["get_persona_profile", "search_memory", "query_knowledge_graph",
           "get_retention_benchmarks"],

    memory_read=MemoryAccessSpec(working=True, episodic=True, semantic=True),
    memory_write=MemoryAccessSpec(working=True, episodic=True, semantic=False),

    events_published=["studio.direction.completed", "studio.direction.low_confidence"],
    events_consumed=[],

    safety_level=SafetyLevel.WRITE,
    approval_required_for=[],
    human_escalation_triggers=["low_confidence_beat_sheet", "novel_format_detected"],

    failure_policy=FailurePolicy(
        tool_failure="retry_once_then_skip",
        llm_failure="retry_with_reasoning_model",
        timeout="abort_and_log",
        invalid_output="retry_with_clarification",
    ),
    max_cycles=5,

    kpis=[
        KPISpec(metric="beat_sheet_confidence", target=0.85, unit="score_0_to_1"),
        KPISpec(metric="downstream_retention_lift", target=0.15, unit="rate_0_to_1"),
    ],
    sla_seconds=15,
)
```

Note `model_label="reasoning"` is set at the department's LLM-call configuration level rather than in the contract's top-level fields — the contract governs orchestration properties; the model label is a call-site parameter, consistent with how SES-002 treats model selection as the platform's routing decision rather than the agent's identity.

---

## 6.5 Output Schema: DirectorialBeatSheet

```python
class Beat(BaseModel):
    beat_id: str
    script_segment_ids: list[str]        # which Script segments this beat covers
    duration_seconds: float
    emotional_target: str                # matches VoicePersona register: default|encourage|correct|celebrate|explain
    camera_direction: str                # "static_medium" | "push_in_slow" | "cut_to_closeup" | "whip_pan"
    pacing_note: str                     # e.g. "hold beat; let the punchline land before cutting"
    retention_hook: str | None           # e.g. "visual pattern interrupt: Mr. Yeti freezes mid-sentence"

class DirectorialBeatSheet(BaseModel):
    beat_sheet_id: str
    production_id: str
    script_id: str
    platform_variant: str                # "9:16" | "16:9" | "1:1"
    beats: list[Beat]
    overall_arc: str                     # one-line description of the emotional arc
    hook_strategy: str                   # what happens in the first 3 seconds
    mid_video_rehook_at_seconds: float | None
    confidence: float                    # AI Director's self-reported confidence, 0.0-1.0
    novel_flags: list[str] = []          # e.g. ["new_topic_area", "unfamiliar_format"]
```

Example beat for the paraphrasing script from Part 5.3:

```json
{
  "beat_id": "beat_1",
  "script_segment_ids": ["seg_1"],
  "duration_seconds": 3.2,
  "emotional_target": "default",
  "camera_direction": "cut_to_closeup",
  "pacing_note": "Open tight on Mr. Yeti's face — the challenge lands harder in closeup than wide.",
  "retention_hook": "Direct address + provocative claim within first 2 seconds, per platform hook benchmark."
}
```

---

## 6.6 Confidence and the Human Review Gate

`confidence` and `novel_flags` are how the AI Director communicates uncertainty upstream rather than silently producing a mediocre beat sheet. A `confidence` below 0.7, or any non-empty `novel_flags`, sets `requires_human_review = True` on the `ProductionState` (Part 2.3) — this is the concrete mechanism behind the "novel content" gate described in Part 1.3. Confidence is computed from: (a) how many similar productions exist in episodic memory to draw on, (b) whether the retention benchmark for this topic/platform combination has enough evidence (`evidence_count >= 3` per SES-003's promotion rule), and (c) a self-critique pass the AI Director runs against its own beat sheet before returning it.

---

# Part 7 — Storyboard Engine

---

## 7.1 Role

The Storyboard Engine takes the AI Director's beat sheet and produces concrete, scene-by-scene visual specifications: composition, character position and expression, background, on-screen text/captions, and the specific asset requirements each scene needs. Where the AI Director answers "how is this told," the Storyboard Engine answers "what does frame one, frame two, frame three actually contain."

Each `Beat` from the beat sheet expands into one or more `StoryboardScene` records — a beat with `pacing_note: "hold beat"` might be a single scene; a beat calling for a `whip_pan` camera direction might require two scenes (before/after the pan) if the target renderer cannot express a whip pan as a single generation prompt.

---

## 7.2 AgentContract: `storyboard_engine_agent`

```python
AgentContract(
    name="storyboard_engine_agent",
    display_name="Storyboard Engine",
    version="1.0.0",
    department="ai_studio",
    parent_agent="studio_director",

    purpose="Expand a directorial beat sheet into concrete scene-by-scene visual specifications.",
    why_it_exists="Rendering backends need a fully concrete scene spec; neither the script nor the beat sheet is specific enough to generate a frame from directly.",
    capabilities_owned=["CAP-044"],
    interfaces_exposed=["internal:studio.storyboard"],
    dependents=["character_agent", "asset_agent", "voice_agent", "renderer_registry"],

    inputs=[
        InputSpec(name="beat_sheet", type="DirectorialBeatSheet", required=True),
    ],
    outputs=[
        OutputSpec(name="storyboard", type="Storyboard"),
    ],
    tools=["get_character_bible", "search_asset_registry", "search_memory"],

    memory_read=MemoryAccessSpec(working=True, episodic=True, semantic=True),
    memory_write=MemoryAccessSpec(working=True, episodic=True, semantic=False),

    events_published=["studio.storyboard.completed", "studio.storyboard.failed"],
    events_consumed=[],

    safety_level=SafetyLevel.WRITE,
    approval_required_for=[],
    human_escalation_triggers=["asset_requirement_unresolvable"],

    failure_policy=FailurePolicy(
        tool_failure="retry_once_then_skip",
        llm_failure="retry_with_reasoning_model",
        timeout="abort_and_log",
        invalid_output="retry_with_clarification",
    ),
    max_cycles=5,

    kpis=[
        KPISpec(metric="scene_render_first_pass_success_rate", target=0.85, unit="rate_0_to_1"),
    ],
    sla_seconds=10,
)
```

---

## 7.3 StoryboardScene Schema

```python
class StoryboardScene(BaseModel):
    scene_id: str
    beat_id: str                          # traces back to DirectorialBeatSheet
    duration_seconds: float
    composition: str                      # "medium_closeup" | "wide" | "closeup" | "over_shoulder"
    character_position: str               # "center" | "left_third" | "right_third"
    character_expression: str             # must exist in the Character Dept's expression library
    background: str                       # asset registry key or generation prompt
    on_screen_text: list[OnScreenText]
    audio_segment_ids: list[str]          # ties to Script segments / Voice Department output
    required_assets: list[str]            # asset registry keys this scene depends on
    render_hints: dict                    # renderer-specific hints, e.g. {"camera_move": "push_in_slow"}

class OnScreenText(BaseModel):
    text: str
    start_seconds: float
    end_seconds: float
    style: str                            # "caption" | "callout" | "keyword_highlight"

class Storyboard(BaseModel):
    storyboard_id: str
    production_id: str
    beat_sheet_id: str
    platform_variant: str
    scenes: list[StoryboardScene]
```

---

# Part 8 — Character Department

---

## 8.1 Role

The Character Department owns character consistency across every generated frame. This is the hardest unsolved problem in AI-generated video content: without a dedicated consistency mechanism, the same character looks meaningfully different from shot to shot — different fur texture, different glasses shape, different proportions — which is immediately, viscerally noticeable to viewers even when they can't articulate why a video "feels off."

For Mr. Yeti, consistency is achieved with **IC-LoRA (In-Context LoRA)** — a lightweight adaptation applied to the image/video generation backend that conditions every generation on a fixed set of reference images and a textual character description, rather than re-describing the character from scratch in every prompt and hoping for consistency.

---

## 8.2 The Character Bible

The character bible is the canonical, versioned source of truth for a character's appearance, personality, and voice. It has four parts:

1. **Canonical description** — a precise, unambiguous textual description used as conditioning text for every render (see Appendix A for Mr. Yeti's full canonical description)
2. **Visual reference set** — a fixed set of reference images spanning multiple angles and lighting conditions, used as the IC-LoRA conditioning images
3. **Expression library** — a named set of expressions (`neutral`, `playful_challenge`, `encouraging_smile`, `mock_serious`, `celebrating`) that the Storyboard Engine's `character_expression` field must reference by name, ensuring the Rendering Department always receives a known, tested expression rather than a freeform description
4. **Voice profile pointer** — a reference to the `mr_yeti` `VoicePersona` defined in SES-004 Part 5.2, so the Character Department is the single place that ties visual and vocal identity together

---

## 8.3 AgentContract: `character_agent`

```python
AgentContract(
    name="character_agent",
    display_name="Character Consistency Agent",
    version="1.0.0",
    department="ai_studio",
    parent_agent="studio_director",

    purpose="Produce IC-LoRA conditioning data and expression-specific character assets for a storyboard's scenes.",
    why_it_exists="Character consistency across generated frames does not happen by default; it requires an explicit conditioning mechanism owned by one department.",
    capabilities_owned=["CAP-045"],
    interfaces_exposed=["internal:studio.character"],
    dependents=["renderer_registry"],

    inputs=[
        InputSpec(name="storyboard", type="Storyboard", required=True),
        InputSpec(name="character_bible_id", type="str", required=True),
    ],
    outputs=[
        OutputSpec(name="character_assets", type="CharacterAssets"),
    ],
    tools=["get_character_bible", "generate_reference_frame", "upload_to_r2"],

    memory_read=MemoryAccessSpec(working=True, episodic=False, semantic=True),
    memory_write=MemoryAccessSpec(working=True, episodic=True, semantic=False),

    events_published=["studio.character.completed", "studio.character.consistency_flagged"],
    events_consumed=[],

    safety_level=SafetyLevel.WRITE,
    approval_required_for=[],
    human_escalation_triggers=["consistency_score_below_threshold"],

    failure_policy=FailurePolicy(
        tool_failure="retry_once_then_skip",
        llm_failure="retry_with_reasoning_model",
        timeout="abort_and_log",
        invalid_output="retry_with_clarification",
    ),
    max_cycles=3,

    kpis=[
        KPISpec(metric="cross_scene_consistency_score", target=0.9, unit="score_0_to_1"),
    ],
    sla_seconds=20,
)
```

---

## 8.4 IC-LoRA Conditioning Flow

```python
class CharacterAssets(BaseModel):
    production_id: str
    character_bible_id: str
    lora_weights_ref: str                 # R2 path to the trained/cached IC-LoRA weights
    conditioning_images: list[str]        # R2 paths, one per angle in the reference set
    per_scene_expression_refs: dict[str, str]   # scene_id -> expression reference image path


class CharacterAgent:
    async def run(self, storyboard: Storyboard, character_bible_id: str) -> DepartmentResult[CharacterAssets]:
        bible = await character_bible_store.get(character_bible_id)

        # IC-LoRA weights are trained once per character and cached — not retrained per production
        lora_weights = await ic_lora_cache.get_or_train(
            character_id=bible.character_id,
            reference_images=bible.visual_reference_set,
            canonical_description=bible.canonical_description,
        )

        expression_refs = {}
        for scene in storyboard.scenes:
            if scene.character_expression not in bible.expression_library:
                return DepartmentResult(output=None, outcome="failure",
                    error=f"Unknown expression: {scene.character_expression}")
            expression_refs[scene.scene_id] = bible.expression_library[scene.character_expression]

        return DepartmentResult(
            output=CharacterAssets(
                production_id=storyboard.production_id,
                character_bible_id=character_bible_id,
                lora_weights_ref=lora_weights.r2_path,
                conditioning_images=bible.visual_reference_set,
                per_scene_expression_refs=expression_refs,
            ),
            outcome="success",
        )
```

Because the IC-LoRA weights are trained once and cached (`get_or_train` short-circuits to a cache hit for every production after the first), the marginal cost of the Character Department per production is near zero — it is primarily a lookup and validation step, not a generation step.

---

# Part 9 — Asset Department

---

## 9.1 Role

The Asset Department manages every reusable visual and audio asset that is not the character itself: backgrounds, props, music beds, sound effects, and fragments from prior renders that can be reused rather than regenerated. Reuse is the department's entire reason for existing — regenerating a classroom background from scratch for every video that needs one is both slower and less consistent than reusing a validated asset from the registry.

---

## 9.2 Asset Registry Schema

```sql
CREATE TABLE asset_registry (
    asset_id        TEXT PRIMARY KEY,
    asset_type      TEXT NOT NULL,        -- background|prop|music_bed|sfx|render_fragment
    name            TEXT NOT NULL,
    tags            TEXT NOT NULL,        -- JSON array, e.g. ["classroom", "warm_lighting", "9:16"]
    r2_path         TEXT NOT NULL,        -- Cloudflare R2 object key
    platform_variants TEXT,               -- JSON: which aspect ratios this asset has pre-rendered
    source           TEXT NOT NULL,       -- generated|licensed|prior_render
    usage_count      INTEGER DEFAULT 0,
    last_used_at     DATETIME,
    quality_score    REAL DEFAULT 1.0,    -- degraded by QA flags; low-quality assets stop being reused
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_asset_type ON asset_registry(asset_type);
CREATE INDEX idx_asset_tags ON asset_registry(tags);
```

---

## 9.3 Cloudflare R2 Storage Integration

All binary asset data — images, audio, video fragments — is stored in Cloudflare R2, consistent with the platform capability registry (SES-000 Part on Capabilities, `CAP: object_storage` = R2). The `asset_registry` table stores only metadata and R2 object keys; no binary data lives in SQLite.

```python
class AssetStore:
    def __init__(self, r2_client: R2Client):
        self.r2 = r2_client

    async def find_or_generate(
        self, asset_type: str, tags: list[str], generate_fn: Callable
    ) -> AssetRecord:
        existing = await db.query_assets(asset_type=asset_type, tags=tags,
                                          min_quality=0.7, order_by="usage_count DESC")
        if existing:
            await db.increment_usage(existing[0].asset_id)
            return existing[0]

        # No suitable reusable asset — generate a new one
        generated = await generate_fn()
        r2_key = f"assets/{asset_type}/{uuid4()}.{generated.ext}"
        await self.r2.put(r2_key, generated.data)

        return await db.insert_asset(AssetRecord(
            asset_id=str(uuid4()), asset_type=asset_type, tags=tags,
            r2_path=r2_key, source="generated", usage_count=1,
        ))
```

Assets whose `quality_score` drops below 0.5 (set by a QA flag — see Part 13) are excluded from `find_or_generate` results but not deleted, preserving the audit trail without contaminating future productions.

---

# Part 10 — Voice Department

---

## 10.1 Role and the Platform-First Principle

The Voice Department generates narration audio for a production. It does not implement text-to-speech, SSML annotation, or a persona system — all of that already exists as a platform capability in SES-004 Voice OS. The Voice Department's entire job is to call that capability correctly: assemble the script's segments and tone markers into the input Voice OS's TTS pipeline expects, invoke it, and hand the resulting audio track downstream.

This is the Platform-First Principle (AP-01, referenced in SES-004's own "Why This Document Exists" section) applied concretely: AI Studio does not build a second TTS integration because it happens to need narration instead of conversational speech. It is one more consumer of OmniVoice, exactly as pielts and the canteen's Baadar assistant are.

---

## 10.2 AgentContract: `voice_agent`

```python
AgentContract(
    name="voice_agent",
    display_name="Studio Voice Agent",
    version="1.0.0",
    department="ai_studio",
    parent_agent="studio_director",

    purpose="Generate narration audio for a production's script using the platform Voice OS TTS capability.",
    why_it_exists="Narration audio must use the same persona, SSML conventions, and TTS backend as every other product; this department is the thin call-site, not a second implementation.",
    capabilities_owned=["CAP-046"],
    interfaces_exposed=["internal:studio.voice"],
    dependents=["renderer_registry"],

    inputs=[
        InputSpec(name="script", type="Script", required=True),
        InputSpec(name="beat_sheet", type="DirectorialBeatSheet", required=True),
    ],
    outputs=[
        OutputSpec(name="voice_track", type="VoiceTrack"),
    ],
    tools=["omnivoice_synthesize", "ssml_annotate"],

    memory_read=MemoryAccessSpec(working=True, episodic=False, semantic=True),
    memory_write=MemoryAccessSpec(working=True, episodic=True, semantic=False),

    events_published=["studio.voice.completed", "studio.voice.failed"],
    events_consumed=[],

    safety_level=SafetyLevel.WRITE,
    approval_required_for=[],
    human_escalation_triggers=["tts_quality_below_threshold"],

    failure_policy=FailurePolicy(
        tool_failure="fallback_to_cloud_tts",
        llm_failure="retry_with_reasoning_model",
        timeout="fallback_to_cloud_tts",
        invalid_output="retry_with_clarification",
    ),
    max_cycles=3,

    kpis=[
        KPISpec(metric="tts_latency_ms", target=5000, unit="ms"),
        KPISpec(metric="timing_drift_ms", target=200, unit="ms"),
    ],
    sla_seconds=10,
)
```

---

## 10.3 Calling Voice OS

```python
class VoiceAgent:
    async def run(self, script: Script, beat_sheet: DirectorialBeatSheet) -> DepartmentResult[VoiceTrack]:
        persona = VOICE_PERSONAS["mr_yeti"]   # defined in SES-004 Part 5.2
        clips = []

        for segment in script.segments:
            beat = next(b for b in beat_sheet.beats if segment.segment_id in b.script_segment_ids)
            ssml = SSMLAnnotator().annotate(
                text=segment.text, persona=persona, register=beat.emotional_target,
            )
            audio_chunk = await omnivoice_tts.synthesize(
                ssml=ssml, voice_id=persona.voice_id, fallback=gemini_tts,
            )
            clips.append(NarrationClip(
                segment_id=segment.segment_id,
                audio_r2_path=await r2.put_audio(audio_chunk),
                duration_seconds=audio_chunk.duration_seconds,
            ))

        return DepartmentResult(
            output=VoiceTrack(production_id=script.production_id, clips=clips),
            outcome="success",
        )
```

The `SSMLAnnotator` and `VOICE_PERSONAS` referenced above are the exact classes defined in SES-004 Parts 5.2 and 5.4 — imported, not reimplemented. If Voice OS's TTS backend changes (a new OmniVoice version, a different fallback provider), the Voice Department requires zero code changes; it calls the platform capability by contract, not by implementation detail.

---

# Part 11 — Rendering Department (Renderer Registry)

---

## 11.1 The Problem: Rendering Backends Change Faster Than Everything Else

Of every layer in AI Studio, the video generation model landscape is the least stable. LTX-2, Open-Sora, Wan, and Veo 2 are current options in mid-2026; Runway Gen-4, Kling, Hailuo, and Minimax are credible near-future additions, and the ranking of "best" backend for a given scene type shifts monthly. A Rendering Department that hardcodes calls to one specific model ties the entire Studio's output quality to that one vendor's roadmap.

The Renderer Registry (see Brain.md Section 8, "Renderer Registry — not hardcoded") solves this with the same abstraction pattern SES-002 uses for LLM providers: an abstract interface every backend implements, and a registry that selects among registered implementations at call time based on cost, quality, and capability requirements — never based on a backend name hardcoded into calling code.

---

## 11.2 The `BaseRenderer` Interface

```python
from abc import ABC, abstractmethod

class RenderCapability(str, Enum):
    TEXT_TO_VIDEO = "text_to_video"
    IMAGE_TO_VIDEO = "image_to_video"
    CHARACTER_CONSISTENCY = "character_consistency"   # IC-LoRA or equivalent conditioning
    CAMERA_CONTROL = "camera_control"                  # explicit push/pan/cut direction
    LONG_FORM = "long_form"                            # > 10 second single clips
    TRANSPARENT_BACKGROUND = "transparent_background"


class RenderedClip(BaseModel):
    clip_id: str
    scene_id: str
    r2_path: str
    duration_seconds: float
    renderer_used: str
    cost_usd: float
    render_time_ms: int


class BaseRenderer(ABC):
    """Every rendering backend implements this interface. The registry and every
    caller depend only on this contract — never on a concrete adapter class."""

    name: str

    @abstractmethod
    async def render_scene(
        self, scene_spec: StoryboardScene, character_assets: CharacterAssets
    ) -> RenderedClip:
        ...

    @abstractmethod
    def estimate_cost(self, scene_spec: StoryboardScene) -> float:
        ...

    @abstractmethod
    def supports_capability(self, cap: RenderCapability) -> bool:
        ...
```

---

## 11.3 Concrete Adapters

Each backend is a thin adapter class that implements `BaseRenderer` and translates the platform's neutral `StoryboardScene` into that backend's specific API shape.

```python
class LTX2Renderer(BaseRenderer):
    name = "ltx2"

    async def render_scene(self, scene_spec, character_assets) -> RenderedClip:
        response = await ltx2_client.generate(
            prompt=self._build_prompt(scene_spec),
            conditioning_images=character_assets.conditioning_images,
            lora_weights=character_assets.lora_weights_ref,
            duration=scene_spec.duration_seconds,
            aspect_ratio=self._aspect_from_render_hints(scene_spec.render_hints),
        )
        return RenderedClip(
            clip_id=str(uuid4()), scene_id=scene_spec.scene_id,
            r2_path=await r2.put_video(response.video_bytes),
            duration_seconds=scene_spec.duration_seconds,
            renderer_used=self.name, cost_usd=response.cost_usd,
            render_time_ms=response.elapsed_ms,
        )

    def estimate_cost(self, scene_spec) -> float:
        return 0.04 * scene_spec.duration_seconds

    def supports_capability(self, cap: RenderCapability) -> bool:
        return cap in {
            RenderCapability.TEXT_TO_VIDEO, RenderCapability.IMAGE_TO_VIDEO,
            RenderCapability.CHARACTER_CONSISTENCY, RenderCapability.CAMERA_CONTROL,
        }


class OpenSoraRenderer(BaseRenderer):
    name = "open_sora"
    # Self-hosted, GPU-local — near-zero marginal cost, lower peak quality
    def estimate_cost(self, scene_spec) -> float:
        return 0.005 * scene_spec.duration_seconds   # amortized compute only

    def supports_capability(self, cap: RenderCapability) -> bool:
        return cap in {RenderCapability.TEXT_TO_VIDEO, RenderCapability.IMAGE_TO_VIDEO}

    async def render_scene(self, scene_spec, character_assets) -> RenderedClip:
        ...  # calls local Open-Sora inference server


class WanRenderer(BaseRenderer):
    name = "wan"
    def supports_capability(self, cap: RenderCapability) -> bool:
        return cap in {RenderCapability.TEXT_TO_VIDEO, RenderCapability.CHARACTER_CONSISTENCY}
    async def render_scene(self, scene_spec, character_assets) -> RenderedClip: ...
    def estimate_cost(self, scene_spec) -> float: return 0.03 * scene_spec.duration_seconds


class ComfyUIRenderer(BaseRenderer):
    name = "comfyui"
    # Local workflow graph execution — used for scenes needing custom pipelines
    # (e.g. transparent-background character cutouts for overlay compositing)
    def supports_capability(self, cap: RenderCapability) -> bool:
        return cap in {RenderCapability.IMAGE_TO_VIDEO, RenderCapability.TRANSPARENT_BACKGROUND}
    async def render_scene(self, scene_spec, character_assets) -> RenderedClip: ...
    def estimate_cost(self, scene_spec) -> float: return 0.01 * scene_spec.duration_seconds


class Veo2Renderer(BaseRenderer):
    name = "veo2"
    # Highest quality, highest cost — reserved for hero shots and hooks
    def supports_capability(self, cap: RenderCapability) -> bool:
        return cap in {
            RenderCapability.TEXT_TO_VIDEO, RenderCapability.CAMERA_CONTROL,
            RenderCapability.LONG_FORM,
        }
    async def render_scene(self, scene_spec, character_assets) -> RenderedClip: ...
    def estimate_cost(self, scene_spec) -> float: return 0.12 * scene_spec.duration_seconds
```

---

## 11.4 The `RendererRegistry`

```python
class RendererRegistry:
    def __init__(self):
        self._renderers: dict[str, BaseRenderer] = {}

    def register(self, renderer: BaseRenderer) -> None:
        self._renderers[renderer.name] = renderer

    def select(
        self,
        scene_spec: StoryboardScene,
        required_capabilities: list[RenderCapability],
        quality_tier: str = "standard",     # "draft" | "standard" | "hero"
        max_cost_usd: float | None = None,
    ) -> BaseRenderer:
        candidates = [
            r for r in self._renderers.values()
            if all(r.supports_capability(cap) for cap in required_capabilities)
        ]
        if max_cost_usd is not None:
            candidates = [r for r in candidates if r.estimate_cost(scene_spec) <= max_cost_usd]
        if not candidates:
            raise NoCompatibleRendererError(required_capabilities)

        if quality_tier == "hero":
            # Prefer highest-cost (proxy for highest-quality) compatible renderer
            return max(candidates, key=lambda r: r.estimate_cost(scene_spec))
        if quality_tier == "draft":
            return min(candidates, key=lambda r: r.estimate_cost(scene_spec))
        # "standard": balance — pick the median-cost compatible renderer
        candidates.sort(key=lambda r: r.estimate_cost(scene_spec))
        return candidates[len(candidates) // 2]


RENDERER_REGISTRY = RendererRegistry()
RENDERER_REGISTRY.register(LTX2Renderer())
RENDERER_REGISTRY.register(OpenSoraRenderer())
RENDERER_REGISTRY.register(WanRenderer())
RENDERER_REGISTRY.register(ComfyUIRenderer())
RENDERER_REGISTRY.register(Veo2Renderer())
```

The Studio Director never imports `LTX2Renderer` or `Veo2Renderer` directly. It calls `RENDERER_REGISTRY.select(scene_spec, required_capabilities=[...], quality_tier=...)` and renders against whatever comes back. This is the exact same shape as SES-002's provider abstraction for LLMs — agents specify intent (capability, quality tier, budget), and the platform decides the concrete implementation.

---

## 11.5 FFmpeg Assembly

Once every `StoryboardScene` has a `RenderedClip`, the individual clips are stitched into the final video by FFmpeg — a deterministic, well-understood step that does not benefit from an abstraction layer the way generative rendering does.

```python
class VideoAssembler:
    async def assemble(
        self, clips: list[RenderedClip], voice_track: VoiceTrack,
        storyboard: Storyboard, platform_variant: str,
    ) -> RenderedVideo:
        clip_paths = [await r2.download_to_tmp(c.r2_path) for c in
                      sorted(clips, key=lambda c: self._scene_order(c.scene_id, storyboard))]
        audio_path = await self._concat_narration(voice_track)

        concat_list = "\n".join(f"file '{p}'" for p in clip_paths)
        concat_file = write_tmp_file(concat_list)

        output_path = f"/tmp/{uuid4()}.mp4"
        await run_ffmpeg([
            "-f", "concat", "-safe", "0", "-i", concat_file,
            "-i", audio_path,
            "-vf", self._burn_in_captions_filter(storyboard),
            "-c:v", "libx264", "-c:a", "aac",
            "-aspect", self._aspect_for(platform_variant),
            output_path,
        ])

        return RenderedVideo(
            production_id=storyboard.production_id,
            r2_path=await r2.put_video_file(output_path),
            duration_seconds=sum(c.duration_seconds for c in clips),
            platform_variant=platform_variant,
        )
```

---

## 11.6 Why This Makes Future Renderers Free to Add

Because every caller depends only on `BaseRenderer` and the `RendererRegistry`, adding Runway Gen-4, Kling, Hailuo, or Minimax as they mature requires exactly one new adapter file implementing three methods, plus one `register()` call at startup — zero changes to the Storyboard Engine, the Studio Director, or any other department. This is worked through concretely in Appendix E.

---

# Part 12 — Real-Time Studio

---

## 12.1 Role

Every department covered so far produces pre-rendered, asynchronous video. Real-Time Studio is different: it produces a live, streamable, interactive Mr. Yeti — an animated avatar that responds to a live audio feed in near-real-time, for use cases like live Q&A streams and real-time tutoring sessions where a pre-rendered video cannot exist because the content isn't known in advance.

Real-Time Studio is not a new interaction paradigm invented for AI Studio. It is the second production instantiation of the **Multimodal Interaction Layer** defined in SES-004 Part "Multimodal Interaction Layer (Architectural Foundation)" — Voice OS was the first. Where Voice OS produces audio-only conversational output, Real-Time Studio adds a synchronized visual layer on top of the same shared MIL capabilities (OmniVoice TTS, VAD, WebRTC, audio buffer).

```
┌─────────────────────────────────────────────────────────────────┐
│               MULTIMODAL INTERACTION LAYER (MIL)                │
│  ┌──────────────┐  ┌──────────────────────────────────────────┐ │
│  │  Voice OS    │  │   Real-Time Studio (this Part)            │ │
│  │  (SES-004)   │  │   Pipecat + PersonaLive/LivePortrait +    │ │
│  │              │  │   WebRTC → streaming animated avatar      │ │
│  └──────┬───────┘  └──────────────────────┬───────────────────┘ │
│         │                                 │                      │
│  ┌──────▼─────────────────────────────────▼───────────────────┐ │
│  │   SHARED: OmniVoice TTS │ VAD │ Pipecat │ WebRTC │ Audio I/O │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 12.2 Pipeline

```
Live audio input (host question, or Voice OS conversational turn)
        │
        ▼
┌─────────────────────────────────────────────┐
│  Pipecat orchestration (SES-004 Part 8)      │
│  — same Pipeline/Processor chain as Voice OS │
└──────────────────────┬────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│  OmniVoice TTS (streaming, sentence-by-      │
│  sentence, mr_yeti persona)                  │
└──────────────────────┬────────────────────────┘
                       │ audio chunks
                       ▼
┌─────────────────────────────────────────────┐
│  PersonaLive / LivePortrait                  │
│  real-time facial animation driven by audio  │
│  — maps audio phonemes/energy to Mr. Yeti's  │
│    IC-LoRA-conditioned facial rig            │
│  Target: < 200ms audio-to-lip-sync latency   │
└──────────────────────┬────────────────────────┘
                       │ video frames
                       ▼
┌─────────────────────────────────────────────┐
│  WebRTC delivery (SES-004's transport layer) │
└──────────────────────┬────────────────────────┘
                       ▼
              Live-streamable animated avatar
```

---

## 12.3 Latency Budget

| Stage | Target |
|-------|--------|
| STT + agent response (via Voice OS pipeline, SES-004 Part 2.1) | < 900ms first-audio |
| TTS audio chunk (OmniVoice, streaming) | < 150ms first chunk |
| PersonaLive/LivePortrait facial animation | < 200ms audio-to-lip-sync |
| WebRTC delivery | < 50ms (local network) / < 150ms (internet) |

The 200ms audio-to-lip-sync target is the binding constraint specific to Real-Time Studio; it is tighter than general video-call latency tolerance because a visible lag between Mr. Yeti's mouth and his voice reads as an animation bug rather than network jitter, breaking the illusion the whole feature depends on.

---

## 12.4 Use Cases

**Live Q&A streams.** Mr. Yeti appears on a YouTube Live or Instagram Live session, taking questions from chat (routed through a moderation queue) and answering live via Voice OS's conversational pipeline with PersonaLive rendering the response in real time.

**Real-time tutoring sessions.** A pielts student in a 1:1 practice session talks to Mr. Yeti and sees him respond live — useful specifically for IELTS Speaking practice, where the student needs to practice speaking to a person-like presence rather than typing.

---

## 12.5 AgentContract: `realtime_studio_agent`

```python
AgentContract(
    name="realtime_studio_agent",
    display_name="Real-Time Studio Agent",
    version="1.0.0",
    department="ai_studio",
    parent_agent="studio_director",

    purpose="Drive a live, audio-synchronized animated Mr. Yeti avatar for streaming and interactive sessions.",
    why_it_exists="Live and interactive appearances cannot use the pre-rendered pipeline; they require a real-time facial animation layer built on the same Multimodal Interaction Layer as Voice OS.",
    capabilities_owned=["CAP-047"],
    interfaces_exposed=["WS /api/v1/studio/realtime"],
    dependents=["mission_control"],

    inputs=[
        InputSpec(name="live_audio_stream", type="AudioStream", required=True),
        InputSpec(name="character_bible_id", type="str", required=True),
    ],
    outputs=[
        OutputSpec(name="video_stream", type="WebRTCStream"),
    ],
    tools=["pipecat_pipeline", "omnivoice_synthesize", "persona_live_render",
           "webrtc_publish"],

    memory_read=MemoryAccessSpec(working=True, episodic=False, semantic=True),
    memory_write=MemoryAccessSpec(working=True, episodic=True, semantic=False),

    events_published=["studio.realtime.session_started", "studio.realtime.session_ended"],
    events_consumed=["voice_os.barge_in"],

    safety_level=SafetyLevel.EXTERNAL,   # publishes a live public-facing stream
    approval_required_for=["session_start_on_new_platform"],
    human_escalation_triggers=["lip_sync_latency_exceeds_400ms", "content_policy_violation_detected"],

    failure_policy=FailurePolicy(
        tool_failure="fallback_to_static_avatar_frame",
        llm_failure="retry_with_reasoning_model",
        timeout="end_session_gracefully",
        invalid_output="retry_with_clarification",
    ),
    max_cycles=None,     # session-duration bound, not cycle-count bound

    kpis=[
        KPISpec(metric="audio_to_lipsync_latency_ms", target=200, unit="ms"),
        KPISpec(metric="session_uptime_rate", target=0.99, unit="rate_0_to_1"),
    ],
    sla_seconds=None,
)
```

---

# Part 13 — QA Department

---

## 13.1 Role

The QA Department is the last automated gate before a production is either published or routed to a human. It runs five checks against the assembled video, none of which is a substitute for the others — a production must pass all five, not a weighted average.

---

## 13.2 QA Checks

| Check | Method | Pass Criterion |
|-------|--------|----------------|
| Audio sync verification | Compare voice track timing markers against final assembled video timestamps | Drift < 100ms across all segments |
| Caption accuracy | Diff burned-in captions against the source Script text | Exact match (post-normalization) ≥ 98% of characters |
| Brand consistency check | Character Department's consistency scorer re-run against sampled frames from the final render | Consistency score ≥ 0.85 across sampled frames |
| Content policy check | `reasoning`-label LLM review against platform content policy (no unverified claims, no disallowed content) | No violations flagged |
| Factual accuracy spot-check | Cross-reference script claims against `research_briefs.fact_check_status` | All claims traced to `verified` status; none `pending` or `flagged` |

---

## 13.3 QA Gate Schema

```python
class QACheckResult(BaseModel):
    check_name: str
    passed: bool
    score: float | None
    details: str | None

class QAResult(BaseModel):
    production_id: str
    checks: list[QACheckResult]
    passed: bool                     # True iff every check passed
    requires_human_review: bool      # set independently of `passed` — see 13.4
    evaluated_at: datetime
```

```python
class QAAgent:
    THRESHOLDS = {
        "audio_sync_drift_ms": 100,
        "caption_accuracy": 0.98,
        "brand_consistency": 0.85,
    }

    async def run(self, video: RenderedVideo, script: Script,
                  research_brief: ResearchBrief) -> DepartmentResult[QAResult]:
        checks = [
            await self._check_audio_sync(video, script),
            await self._check_captions(video, script),
            await self._check_brand_consistency(video),
            await self._check_content_policy(script),
            await self._check_factual_accuracy(script, research_brief),
        ]
        passed = all(c.passed for c in checks)
        return DepartmentResult(
            output=QAResult(
                production_id=video.production_id, checks=checks, passed=passed,
                requires_human_review=research_brief.is_high_stakes or not passed,
                evaluated_at=datetime.utcnow(),
            ),
            outcome="success" if passed else "failure",
        )
```

---

## 13.4 Pass/Fail Criteria and Escalation

A production that fails any check returns to the Studio Director as `route_on_qa -> "fail"` (Part 2.3), which routes into the `retry` node targeting the specific department responsible for that failure (audio sync failure retries Voice/Rendering; caption failure retries Rendering's burn-in step; content policy failure retries Script). A production that passes every check but was flagged `is_high_stakes` by Research (Part 4.4) or `novel_flags` by the AI Director (Part 6.6) still routes to `human_review` rather than directly to Publishing — passing QA does not override the human-gate conditions established in Part 1.3.

---

# Part 14 — Publishing Department

---

## 14.1 Role

The Publishing Department takes an approved video and gets it in front of an audience: YouTube, TikTok, Instagram, and Facebook, each with its own format requirements and posting mechanics. Publishing is also the integration point with the Discovery Engine's pre-publish optimization gate — before anything goes out, SES-010's discovery layer gets a chance to adjust metadata for maximum discoverability.

**Cross-reference: SES-010 Discovery Engine pre-publish gate.** Publishing calls `discovery_engine.optimize_pre_publish(video, metadata)` before the platform-specific publish calls. This is not a QA check (Part 13 already ran) — it is a metadata and discoverability optimization pass: title variants, tag selection, thumbnail candidate scoring, and posting-time recommendation, informed by SES-010's cross-channel discoverability signals (SEO, AI Search, YouTube, Social, App Store — treated as one Discovery Engine per Brain.md Section 8, not as "SEO" alone).

---

## 14.2 Platform-Specific Format Adaptation

| Platform | Aspect Ratio | Max Duration | Caption Handling | Thumbnail |
|----------|-------------|--------------|-------------------|-----------|
| YouTube Shorts | 9:16 | 60s | Burned-in + separate SRT upload | Auto-generated from hook frame |
| TikTok | 9:16 | 60s (routine), up to 10m (long-form pilot) | Burned-in required | Platform auto-selects; override via API |
| Instagram Reels | 9:16 | 90s | Burned-in + accessibility captions | Auto-generated from hook frame |
| Facebook | 9:16 or 16:9 | Platform default | Burned-in | Auto-generated |
| YouTube (long-form) | 16:9 | 3–8 min | Burned-in + SRT | Custom-composited from storyboard hero scene |

---

## 14.3 Scheduling Integration

Publishing does not decide *when* to post on its own — it hands the approved, format-adapted video to SaathiAI's existing scheduler (the same scheduler that drives the platform's daily content queue), which owns posting-time decisions across all content types, not just AI Studio output. This keeps posting cadence and timing strategy in one place rather than duplicated per content source.

```python
class PublishingAgent:
    async def run(self, video: RenderedVideo, brief: ContentBrief) -> DepartmentResult[PublishResult]:
        results = {}
        for platform in brief.target_platforms:
            adapted = await self._adapt_for_platform(video, platform)
            metadata = await discovery_engine.optimize_pre_publish(adapted, base_metadata(brief))
            scheduled = await scheduler.enqueue(
                content=adapted, metadata=metadata, platform=platform,
                content_type="ai_studio_video",
            )
            results[platform] = scheduled

        return DepartmentResult(
            output=PublishResult(production_id=video.production_id, platform_results=results),
            outcome="success",
        )
```

---

# Part 15 — Analytics Department

---

## 15.1 Role

The Analytics Department tracks per-video performance after publishing — views, the retention curve (what fraction of viewers were still watching at each second), and engagement (likes, comments, shares, saves) — and feeds that data both into the Self-Improvement Loop (Part 16) and directly into SES-003 Memory as episodic entries.

---

## 15.2 Performance Tracking

```python
class PerformanceReport(BaseModel):
    production_id: str
    platform: str
    views: int
    retention_curve: list[float]        # % of viewers remaining at each second, index 0 = 100%
    likes: int
    comments: int
    shares: int
    saves: int
    watch_time_seconds: float
    collected_at: datetime


class AnalyticsAgent:
    async def run(self, production_id: str) -> DepartmentResult[list[PerformanceReport]]:
        reports = []
        for platform in await db.get_publish_platforms(production_id):
            metrics = await platform_apis[platform].fetch_metrics(production_id)
            reports.append(PerformanceReport(production_id=production_id, platform=platform, **metrics))

        # Write to SES-003 Episodic Memory — one entry per production, not per platform
        await episodic_memory.write(EpisodicEntry(
            agent="analytics_agent", department="ai_studio", product="mr_yeti",
            session_id=production_id, intent="content_performance_tracked",
            content=json.dumps([r.dict() for r in reports]),
            outcome="success", created_at=datetime.utcnow(),
        ))
        return DepartmentResult(output=reports, outcome="success")
```

---

## 15.3 Feeding Memory: Promoted Patterns

The raw `PerformanceReport` records are not directly useful as context for future productions — they need to be compressed into patterns, following the exact promotion path defined in SES-003 Part 4 (Memory Promotion Engine). A pattern like `"hooks under 3 seconds outperform"` is exactly the shape of `SemanticPattern` category `performance` described in SES-003 Part 1.2 ("Question 4: What should be summarized?").

| Raw observation (across ≥3 productions) | Promoted `semantic_pattern` |
|---|---|
| Videos with hook duration < 3s show 22% higher 3-second retention | `pattern_key=hook_duration_under_3s_improves_retention, category=performance, scope=product:mr_yeti` |
| Videos using `cut_to_closeup` on the hook beat outperform `static_medium` by 15% | `pattern_key=closeup_hook_camera_direction_wins, category=performance, scope=product:mr_yeti` |
| Thumbnails with Mr. Yeti's `playful_challenge` expression get higher CTR than `neutral` | `pattern_key=playful_challenge_thumbnail_ctr, category=performance, scope=product:mr_yeti` |

This is the same Memory Promotion Engine described in SES-003 Part 4.3 — Analytics does not implement its own promotion logic; it writes qualifying episodic entries and lets the daily promotion job do the extraction, keeping the promotion algorithm in one place across the whole platform.

---

# Part 16 — Self-Improvement Loop

---

## 16.1 Role

The Self-Improvement Loop is what makes the second hundred Mr. Yeti videos better than the first hundred, without a human rewriting the Script Department's prompts or the AI Director's heuristics by hand. It closes the loop shown in Part 2.1's pipeline diagram: Analytics feeds performance data forward, the Loop analyzes which productions performed well, extracts the patterns responsible, writes them as `semantic_patterns` per SES-003's Memory Promotion Engine, and injects them back into the Context Assembly Engine calls that the Script Department and AI Director make for future productions.

This is the concrete instantiation, for AI Studio, of the platform's broader "intelligence compounds" mission (SES-000 Master Roadmap) — the same principle that governs the Learning Engine in SES-003 Part 8, applied specifically to content performance rather than general operational patterns.

---

## 16.2 The Loop

```
Published productions (LIVE state, 7-day performance window elapsed)
        │
        ▼
Analytics Department writes PerformanceReport → episodic_memory (Part 15)
        │
        │  Memory Promotion Engine (SES-003 Part 4.3) — daily job
        ▼
Candidate performance patterns in L2 Semantic Memory
        │
        │  Learning Engine (SES-003 Part 8) — evidence_count >= 3, confidence >= 0.8
        ▼
Verified performance knowledge — e.g. "hooks under 3s outperform"
        │
        │  Self-Improvement Loop: capability update proposal (SES-003 Part 8.2, Phase 5)
        ▼
Context Assembly Engine injection:
    - AI Director's Context Assembly call now surfaces verified retention patterns
      as Priority-7 semantic_patterns (SES-003 Part 5.2)
    - Script Department's Context Assembly call surfaces verified hook-phrasing
      and topic-performance patterns the same way
        │
        ▼
Next production's beat sheet and script are written with this knowledge already
in context — no prompt was hand-edited; the platform's own memory did the work
```

---

## 16.3 What Gets Extracted

The Self-Improvement Loop does not re-derive new categories of pattern beyond what SES-003's Learning Engine already supports — it is a domain-specific consumer of that general mechanism, scoped to the `mr_yeti` and `ai_studio` scopes. The categories most relevant to AI Studio:

- **Beat structures** — which `camera_direction` / `pacing_note` combinations at the hook beat correlate with retention (feeds the AI Director)
- **Hook phrasing patterns** — which script hook styles (`playful_challenge` vs. `direct_question` vs. `provocative_claim`) correlate with 3-second retention (feeds the Script Department)
- **Thumbnail/expression styles** — which character expressions used in thumbnails correlate with click-through rate (feeds the Character Department's thumbnail candidate generation, called from Publishing's pre-publish step)
- **Topic performance** — which IELTS sub-topics reliably outperform others, informing which briefs the Studio Director accepts at higher priority from the future Dream Engine

---

## 16.4 Implementation

```python
class StudioSelfImprovementLoop:
    """Runs after the daily Memory Promotion Engine and Learning Engine jobs (SES-003 Part 4, 8)."""

    async def run(self) -> SelfImprovementReport:
        report = SelfImprovementReport(run_at=datetime.utcnow())

        verified_patterns = await self.kg.get_newly_verified(scope_prefix="product:mr_yeti")
        for pattern in verified_patterns:
            if pattern.category != "performance":
                continue

            # Determine which department context this pattern should be injected into
            target_departments = self._classify_target(pattern)
            for dept in target_departments:
                await context_assembly_config.register_semantic_boost(
                    department=dept, pattern_key=pattern.pattern_key,
                    scope="product:mr_yeti",
                )
                report.patterns_wired += 1

        return report

    def _classify_target(self, pattern: SemanticPattern) -> list[str]:
        if "hook" in pattern.pattern_key or "camera" in pattern.pattern_key:
            return ["ai_director_agent"]
        if "phrasing" in pattern.pattern_key or "topic" in pattern.pattern_key:
            return ["script_agent"]
        if "thumbnail" in pattern.pattern_key or "expression" in pattern.pattern_key:
            return ["character_agent"]
        return []
```

`context_assembly_config.register_semantic_boost` does not modify any agent's prompt text. It adjusts which `semantic_patterns` rows the Context Assembly Engine's Priority-7 layer (SES-003 Part 5.2) retrieves for that department's future calls — the improvement mechanism is entirely data-driven, consistent with SES-003's principle that memory is a shared platform resource (M-P3) rather than a per-agent hardcoded rule set.

---

# Appendix A — Mr. Yeti Full Production Spec

---

## A.1 Character Bible — Canonical Description

> Mr. Yeti is a large, gentle, expressive yeti standing upright with a slightly rounded, approachable build. His fur is bright white with a soft, slightly tousled texture — not sleek, not cartoonishly fluffy. He wears round, thin-wire glasses that sit low on his snout, and a well-fitted but slightly rumpled brown tweed teacher's suit jacket over a simple collared shirt, no tie. His expression defaults to warm curiosity, with expressive eyebrows that do most of his emotional work. He gestures with his hands frequently while explaining. He does not wear shoes. Color palette: white fur, brown jacket, cream shirt, warm amber glasses frames.

**Personality traits:** warm, funny, a little theatrical, genuinely delighted by language, patient but not saccharine, treats mistakes as interesting rather than shameful.

**Catchphrases:** "Big mistake, big opportunity." (used when correcting a common student error) · "Let's yeti this." (used as a segment transition, played for groans) · "Band 9 energy." (used as an encouragement marker when a student technique is demonstrated correctly)

**Voice persona reference:** `mr_yeti` `VoicePersona`, defined in full in SES-004 Part 5.2 — speaking rate 0.95, pitch shift -1.0 semitones, energy level 0.7, five registers (`default`, `encourage`, `correct`, `celebrate`, `explain`).

---

## A.2 Example Full Production Walkthrough

**Brief:** `topic="paraphrasing techniques for IELTS Writing Task 2", target_platforms=["youtube_shorts", "tiktok", "instagram_reels"]`

1. **Research** gathers the Band 7 Lexical Resource descriptor, notes that most competitor content teaches synonym-swapping rather than sentence restructuring, and flags no high-stakes claims (`is_high_stakes = 0`).
2. **Script** writes a 96-word, 42-second script with a `playful_challenge` hook, one `explain` segment, one `example` segment, and an `encourage` CTA (full script shown in Part 5.3).
3. **AI Director** produces a 4-beat sheet: closeup challenge hook (3.2s), medium explain shot (3.8s), split-screen before/after example (5.5s), medium encourage CTA (4.0s), with `confidence = 0.91` (no human review required).
4. **Storyboard** expands the 4 beats into 5 scenes (the example beat splits into "before" and "after" scenes for the split-screen effect), with on-screen text `"many people think" → "it is widely believed that"` timed to the narration.
5. **Character** resolves cached IC-LoRA weights for `mr_yeti` (no new training needed) and returns expression references for `playful_challenge`, `explain`, and `encouraging_smile`.
6. **Asset** reuses an existing "warm classroom, 9:16" background (usage_count incremented) rather than generating a new one.
7. **Voice** synthesizes five narration clips via OmniVoice using the `mr_yeti` persona, one per script segment/register.
8. **Rendering** selects `LTX2Renderer` for the hook and CTA scenes (camera-control capability needed) and `OpenSoraRenderer` for the two example scenes (lower cost, static composition sufficient), then FFmpeg-assembles the five clips with the narration track and burned-in captions.
9. **QA** passes all five checks; `research_brief.is_high_stakes = 0` and `beat_sheet.confidence = 0.91`, so no human review gate triggers.
10. **Publishing** adapts the master 9:16 render for YouTube Shorts, TikTok, and Instagram Reels, runs SES-010's pre-publish optimization for title/tag variants, and hands off to the scheduler.
11. **Analytics** collects a 7-day performance window; the video's sub-3-second hook and 22% above-baseline retention become a candidate `semantic_pattern`.
12. **Self-Improvement Loop** promotes that pattern after a third confirming production and wires it into the AI Director's context for all future hook-beat decisions.

---

# Appendix B — Cost Model

---

## B.1 Per-Production Cost Breakdown

| Component | Typical Cost (USD) | Notes |
|-----------|--------------------|-------|
| Research LLM calls | $0.03 | `standard` label, 2–3 calls (web research summarization, fact-check) |
| Script LLM calls | $0.02 | `standard` label, single generation pass |
| AI Director LLM calls | $0.08 | `reasoning` label — higher per-token cost, justified by directorial quality |
| Storyboard Engine LLM calls | $0.02 | `standard` label |
| Character Department | $0.00 (amortized) | IC-LoRA weights trained once per character, cached indefinitely |
| Rendering (5 scenes, mixed backends per Appendix A example) | $0.85 | 2 scenes on Veo2/LTX-2 tier (~$0.30 combined), 2 scenes on Open-Sora (~$0.04 combined), plus a hero shot; varies significantly by `quality_tier` |
| Voice (OmniVoice, local) | $0.00 | Local inference; near-zero marginal cost per SES-004 |
| Asset storage/retrieval (R2) | $0.01 | Storage + egress, amortized over asset reuse |
| QA (content policy + factual accuracy LLM check) | $0.02 | `standard` label |
| Publishing / Discovery Engine optimization | $0.02 | `standard` label metadata generation |
| **Total typical cost per short-form production** | **≈ $1.05** | Well within the default `budget_ceiling_usd = 3.00` (Part 4.2) |

---

## B.2 Target Cost-Per-Video Budget

| Tier | Target Cost | Use Case |
|------|-------------|----------|
| Draft tier | < $0.50 | Rapid iteration, A/B script variants before committing to a full render |
| Standard tier (default) | $1.00–$2.00 | Routine daily Mr. Yeti Shorts content |
| Hero tier | $3.00–$6.00 | Flagship weekly video, competition entries, launch content |

The Studio Director's `budget_ceiling_usd` (default $3.00, Part 4.2) is set above the standard-tier target to leave headroom for retries (Appendix D) without triggering the 120% overrun escalation on a single retry.

---

# Appendix C — Pipeline Examples

---

## C.1 Example 1 — Simple IELTS Tip Short (Low Complexity)

**Brief:** "one quick tip for Speaking Part 1" · 20 seconds · single platform (TikTok)

- Research: minimal — one verified tip, no competitor analysis needed (topic well-covered in memory already)
- Script: 2 segments (hook + tip), no CTA needed given short runtime
- AI Director: single beat, `static_medium` composition, `confidence = 0.95` (well-worn format)
- Storyboard: 1 scene
- Rendering: `OpenSoraRenderer` (draft tier sufficient for a static talking-head style shot)
- Total estimated cost: ≈ $0.35 · Total pipeline time: ≈ 6 minutes

---

## C.2 Example 2 — Medium Explainer (Moderate Complexity)

**Brief:** "how IELTS Writing Task 2 is actually scored" · 55 seconds · three platforms

- Research: full pass — band descriptors, competitor gap analysis, fact-check against Knowledge Graph `VerifiedFact` nodes for scoring claims (`is_high_stakes = 1` due to scoring claims — routes to human review regardless of QA outcome)
- Script: 5 segments including two examples
- AI Director: 6 beats, mixed `cut_to_closeup` and `push_in_slow`, `confidence = 0.88`
- Storyboard: 7 scenes (one beat splits for a comparison shot)
- Rendering: mixed tier — `LTX2Renderer` for hook and comparison beats, `WanRenderer` for explain beats
- QA: passes all five checks, but `requires_human_review = True` from Research's high-stakes flag — routed to human review gate before publish
- Total estimated cost: ≈ $1.60 · Total pipeline time: ≈ 18 minutes + human review latency

---

## C.3 Example 3 — Complex Multi-Scene Narrative (High Complexity)

**Brief:** "a day in the life of an IELTS examiner" (long-form, narrative, comedic) · 6 minutes · YouTube long-form

- Research: full pass plus additional narrative-structure research (comedic pacing references)
- Script: 22 segments across a three-act structure
- AI Director: 18 beats with a full emotional arc (`overall_arc` describes rising absurdity then a sincere close), `mid_video_rehook_at_seconds` set given the 6-minute runtime, `novel_flags = ["new_format: long_form_narrative"]` — routes to human review as a novel format regardless of confidence score
- Storyboard: 24 scenes, several requiring `TRANSPARENT_BACKGROUND` capability (overlay compositing for a "examiner's clipboard notes" recurring visual motif) — routed to `ComfyUIRenderer`
- Character: multiple expression references per scene given the wider emotional range
- Rendering: `Veo2Renderer` for hero comedic beats, `LTX2Renderer` for standard dialogue beats, `ComfyUIRenderer` for overlay compositing scenes
- Total estimated cost: ≈ $5.20 · Total pipeline time: ≈ 55 minutes + human review latency (novel format gate)

---

# Appendix D — Failure Recovery

---

## D.1 Per-Department Failure Behavior

| Department | Failure Mode | Retry Policy | Fallback |
|-----------|--------------|-------------|----------|
| Research | Web research tool timeout/error | Retry once, then proceed with partial brief flagged `is_high_stakes=1` | Escalate if fact-check confidence stays below threshold after retry |
| Script | LLM generation failure or policy violation | Retry with `reasoning` model | Escalate to human after 2 failures |
| AI Director | Low-confidence or invalid beat sheet | Retry once with expanded memory context | Route to human review rather than retry indefinitely |
| Storyboard | Unresolvable asset requirement | Retry with relaxed asset constraints (allow generation instead of reuse) | Escalate if still unresolvable |
| Character | IC-LoRA weights cache miss and training failure | Retry training once | Escalate — cannot proceed without character assets |
| Asset | R2 upload/retrieval failure | Retry with exponential backoff, max 3 | Escalate after 3 failures |
| Voice | OmniVoice local failure | Immediate fallback to Gemini/ElevenLabs cloud TTS (per SES-004 Part 2.4) | No further fallback; escalate if cloud TTS also fails |
| Rendering | Selected renderer failure or timeout | Re-select via `RendererRegistry` excluding the failed renderer | Escalate if no compatible renderer remains |
| QA | Any check fails | Route back to the owning department (audio sync → Voice/Rendering; captions → Rendering; brand consistency → Character/Rendering; content policy → Script; factual accuracy → Research) | Escalate after 2 full QA failure cycles |
| Publishing | Platform API failure | Retry with backoff, max 3; other platforms in the brief still proceed independently | Escalate the failed platform only; do not block successful platforms |

---

## D.2 Partial Production Recovery

Because the Studio Director's LangGraph is checkpointed via `SqliteSaver` after every node (Part 2.3), a production that fails or is interrupted (process crash, deploy restart) resumes from the last successfully completed state rather than restarting from `BRIEFED`. The Production State Machine (Part 2.2) is the addressable resume point: a production in `FAILED` at the `IN_PRODUCTION` stage retries only the departments that had not yet reported `success` — if Character and Asset both completed but Voice failed, `RETRYING` re-enters only the Voice call, not Character or Asset.

```python
async def retry_node(state: ProductionState) -> ProductionState:
    state["retry_count"] += 1
    if state["retry_count"] > MAX_RETRIES:
        await notify_human_review(state["production_id"], reason="max_retries_exceeded")
        return {**state, "state": "FAILED"}

    resume_target = RESUME_TARGET_BY_FAILED_STAGE[state["state"]]
    return {**state, "state": resume_target, "last_error": None}
```

## D.3 Human Escalation Triggers Summary

Every department's `human_escalation_triggers` field (see each AgentContract in Parts 3–14) feeds a single escalation channel: `notify_human_review`, which posts to Mission Control (SES-007) and, per SES-004's alert conventions, to Telegram. Escalations do not halt other in-flight productions — the Studio Director tracks each `production_id` independently.

---

# Appendix E — Future Rendering Engines

---

## E.1 Adding Runway Gen-4, Kling, Hailuo, or Minimax

The entire cost of adding a new rendering backend to AI Studio is one file. No change is required to the Storyboard Engine, the Studio Director, the `RendererRegistry` class itself, or any AgentContract.

**Step 1 — Implement `BaseRenderer`:**

```python
# app/studio/rendering/adapters/runway_gen4.py

class RunwayGen4Renderer(BaseRenderer):
    name = "runway_gen4"

    async def render_scene(
        self, scene_spec: StoryboardScene, character_assets: CharacterAssets
    ) -> RenderedClip:
        response = await runway_client.generate_gen4(
            prompt=self._build_prompt(scene_spec),
            reference_images=character_assets.conditioning_images,
            duration=scene_spec.duration_seconds,
            camera_motion=scene_spec.render_hints.get("camera_move"),
        )
        return RenderedClip(
            clip_id=str(uuid4()), scene_id=scene_spec.scene_id,
            r2_path=await r2.put_video(response.video_bytes),
            duration_seconds=scene_spec.duration_seconds,
            renderer_used=self.name, cost_usd=response.cost_usd,
            render_time_ms=response.elapsed_ms,
        )

    def estimate_cost(self, scene_spec: StoryboardScene) -> float:
        return 0.09 * scene_spec.duration_seconds

    def supports_capability(self, cap: RenderCapability) -> bool:
        return cap in {
            RenderCapability.TEXT_TO_VIDEO, RenderCapability.IMAGE_TO_VIDEO,
            RenderCapability.CAMERA_CONTROL, RenderCapability.CHARACTER_CONSISTENCY,
        }
```

**Step 2 — Register it at startup:**

```python
# app/studio/rendering/registry_bootstrap.py

RENDERER_REGISTRY.register(RunwayGen4Renderer())
RENDERER_REGISTRY.register(KlingRenderer())     # same pattern
RENDERER_REGISTRY.register(HailuoRenderer())    # same pattern
RENDERER_REGISTRY.register(MinimaxRenderer())   # same pattern
```

**Step 3 — Nothing else.** The next time the Studio Director calls `RENDERER_REGISTRY.select(scene_spec, required_capabilities=[...], quality_tier="hero")`, `RunwayGen4Renderer` becomes a candidate automatically if it reports the right capabilities and fits the cost ceiling. Existing productions, existing storyboards, and every other department are unaffected. This is the entire point of the Renderer Registry pattern established in Part 11 — the abstraction cost is paid once, at design time, so every future rendering engine is a bounded, low-risk addition rather than a cross-cutting change.

---

---

## Closing Note

AI Studio is the flagship consumer of nearly every platform capability documented so far: SES-002's agent contracts and BMA loop govern every department; SES-003's memory tiers store every production and promote every performance pattern; SES-004's Multimodal Interaction Layer powers both narration and the Real-Time Studio's live avatar. Nothing in this document introduces a new foundational primitive — its contribution is the organizational shape that turns those primitives into a working, autonomous content production department, and the two additions (the AI Director and the Renderer Registry) that make that department's output good and its rendering backend replaceable, respectively.

This document is Maturity L1 (Draft pending review). It should be revisited once the first thirty Mr. Yeti productions have run through the full pipeline end to end — at that point, the AI Director's confidence calibration, the QA thresholds in Part 13.2, and the cost model in Appendix B should all be re-validated against real production data rather than the estimates used here.

---

*End of SES-005 — AI Studio.*
