```
================================================================================
SaathiAI Engineering Specification (SES)
================================================================================
Document Title      : Cognitive Memory Architecture
Document ID         : SES-003
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
| 1.0.0 | 2026-07-02 | Ajay Chaulagain | Approved — 10-section Cognitive Memory Architecture |

---

## Why This Document Exists

SES-001 tells us where everything lives.
SES-002 tells us how everything thinks.
This document tells us how everything **remembers** — and how remembering produces improvement.

An agent system without memory is a sophisticated autocomplete. It processes each request in isolation, applies no accumulated understanding of the user, the domain, or its own past decisions, and produces outputs that are no better on day 1,000 than on day 1. It is expensive and it does not learn.

Memory is what separates SaathiAI from a stateless API wrapper. The agent system (SES-002) defines the cognitive loop. This document defines what fills that loop — the substrate of accumulated experience that makes each iteration smarter than the last.

Every product goal that depends on improvement over time depends on this document:
- Mr. Yeti's narration voice becoming more consistent over months of videos
- pielts scoring becoming more aligned with human examiners over thousands of evaluations
- The Daily Content Pipeline producing better-performing posts because it remembers which topics worked
- The HCG canteen system learning its own peak hours and staffing patterns

None of that happens without a formal Cognitive Memory Architecture.

---

## Audience

| Role | Required Sections | Notes |
|------|------------------|-------|
| All Engineers | Parts 1–5 | Core architecture that affects every agent implementation |
| Agent System Engineers | Parts 2–6, 8 | Memory tiers, retrieval, and learning |
| Knowledge Graph Engineers | Parts 3, 8, 9 | Neo4j schema and graph operations |
| Privacy / Governance | Part 7 | Retention, deletion, auditability |
| Product Architects | Parts 1, 9, 10 | Cross-product knowledge and future roadmap |

---

## Reading Order

```
SES-002 Agent System (Part 7 — Memory Access Policy)
        │
        ▼
SES-003 Cognitive Memory Architecture  ← You are here
        │
        ▼
SES-004 Voice OS  (conversational continuity via memory)
SES-005 AI Studio (creative consistency, asset reuse)
SES-006 Video Pipeline (character and storyboard retrieval)
SES-007 Character System (persistent identity, multimodal memory)
```

---

## Document Structure

| Part | Title | The Question It Answers |
|------|-------|------------------------|
| 1 | Memory Philosophy | Why does memory exist? What are the rules of remembering? |
| 2 | Memory Hierarchy | How many tiers? What are the rules for each? |
| 3 | Knowledge Graph | How are entities and relationships stored and queried? |
| 4 | Memory Promotion Engine | How does experience become knowledge? |
| 5 | Context Assembly Engine | How is memory assembled before each LLM call? |
| 6 | Retrieval Pipeline | How does the system find what it needs from memory? |
| 7 | Memory Governance | Who owns the data? Who can delete it? What expires? |
| 8 | Learning Engine | How does the platform improve from what it observes? |
| 9 | Cross-Product Knowledge | How is knowledge shared between products safely? |
| 10 | Future Memory | Multi-user, federated, multimodal, distributed |
| Appendix A | Knowledge Evolution Pipeline | Raw event → Engineering Rule |

---

# Part 1 — Memory Philosophy

---

## 1.1 The Problem Memory Solves

Every LLM call without memory starts from scratch. The model knows everything it learned during training and nothing about the specific context it has been operating in. It does not know that the user prefers concise feedback. It does not know that the last video got 10,000 views because of a particular hook structure. It does not know that a specific API call pattern caused a production failure three weeks ago.

Memory is the mechanism by which accumulated operational experience — millions of individual observations — becomes durable platform intelligence that improves every future decision.

---

## 1.2 Five Memory Questions

Before any memory system is designed, five questions must be answered. The answers to these questions define the entire architecture that follows.

---

### Question 1: Why does memory exist?

Memory exists to make the next action better than the last.

Not to build a historical archive. Not to store everything that has ever happened. Not to comply with an audit requirement. Memory exists for one purpose: **to improve the quality of future decisions by providing relevant context from past experience.**

Every design decision in this document is evaluated against this purpose. A memory that is stored but never retrieved does not serve the purpose. A retention period that keeps data longer than it is useful wastes resources and creates governance risk. A retrieval system that surfaces irrelevant context degrades decisions rather than improving them.

---

### Question 2: What should never be forgotten?

Some information, once learned, is foundational to all future behavior. It should not expire, should not be summarized away, and should survive any cleanup operation.

**Never-forget categories:**

| Category | Examples | Why Never Forget |
|----------|---------|-----------------|
| Engineering rules | "This API requires rate limiting to 5 req/min or it fails with 429" | Hard-won operational knowledge that prevents repeating failures |
| Platform capabilities | "OmniVoice achieves ~50ms TTS latency on this machine" | Calibration data for planning and SLA commitments |
| Product identity | "Mr. Yeti speaks with warmth and humor, not formality" | Brand consistency requires persistence |
| User preferences | "This operator prefers concise Telegram alerts, not verbose ones" | Violating learned preferences degrades trust |
| Security incidents | "Credential X was exposed; rotated on 2026-03-15" | Safety record |
| Verified facts about the domain | "IELTS band 7 requires: coherence, range, accuracy, fluency" | Rubric stability requires stable knowledge |

These entries receive `retention_policy: PERMANENT` and are excluded from all automated cleanup.

---

### Question 3: What should expire?

Operational detail that was useful at one time but becomes noise with age should expire automatically.

**Expiry candidates:**

| Category | Default Lifetime | Why Expire |
|----------|-----------------|-----------|
| Raw session transcripts | 90 days | Summarized content is retained; verbatim transcript adds storage without value |
| Tool call logs (verbose) | 30 days | Patterns are extracted to semantic memory; raw logs are operational data |
| Draft content (unpublished) | 14 days | Drafts that were not published are unlikely to be useful |
| Intermediate research results | 7 days | Final synthesis is retained; raw search results expire |
| Scheduler job logs (per-run) | 60 days | Job history patterns are retained; per-run logs are operational |
| Working memory | Session end | Working memory is strictly session-scoped |

Expiry does not mean deletion. It means **promotion or archival**. Before any record expires, the Memory Promotion Engine (Part 4) evaluates whether it contains anything worth extracting to a higher tier.

---

### Question 4: What should be summarized?

Between "never forget" and "let expire," there is a third category: information that is valuable in compressed form but wasteful in full detail.

**Summarization candidates:**

| What | Summarized to | Example |
|------|--------------|---------|
| 20 conversations about a topic | One semantic summary | "User consistently asks for shorter feedback responses" |
| 100 IELTS evaluation sessions | Pattern extraction | "Band 7 responses average 280 words with 3–4 coherence devices" |
| 50 content publishing events | Performance pattern | "Posts published 6–8 PM outperform posts published at other times by 40%" |
| A week of voice sessions | User profile update | "User speaks with Nepali accent; STT performs better with Whisper medium model" |

Summarization is handled by the Memory Promotion Engine. The promotion decision — when to summarize, what to extract, what to discard — is the most intellectually complex part of the memory architecture.

---

### Question 5: What should become knowledge?

The highest form of memory transformation is when an observation, confirmed across enough instances, stops being a remembered event and becomes a platform rule that governs future behavior.

**The knowledge promotion test:**

A memory entry graduates to platform knowledge when it satisfies all three:
1. **Recurrence** — observed in 3 or more independent instances
2. **Verification** — confirmed by a QA agent evaluation (not inferred by the observing agent)
3. **Generalizability** — applicable across contexts, not specific to one session or user

**Examples:**

| Observation (×3 or more) | Graduated Knowledge |
|--------------------------|-------------------|
| "Groq returns empty content when temperature > 1.2" | `ENGINEERING_RULE: groq_max_temperature = 1.0` |
| "IELTS band scores from Gemini multimodal consistently underestimate Speaking by 0.5 bands" | `CALIBRATION: gemini_speaking_score_bias = +0.5` |
| "Mr. Yeti videos with a question hook in the first 3 seconds achieve 2× retention" | `CONTENT_RULE: mr_yeti_hook_type = question` |

Graduated knowledge is written to the Knowledge Graph as a `PlatformRule` node.

---

## 1.3 Memory Design Principles

**M-P1: Retrieve before generating.** Before any LLM generates a response, relevant memory is assembled. An agent that generates without consulting memory wastes the platform's accumulated intelligence.

**M-P2: Promote before expiring.** No memory record expires until the Memory Promotion Engine has evaluated it. Automatic expiry without promotion evaluation is a data loss policy.

**M-P3: Memory is a shared platform resource.** Memory does not belong to a specific product or agent. An insight from a pielts session that is relevant to the content pipeline is platform knowledge, not pielts knowledge.

**M-P4: Quality over quantity.** A knowledge graph with 100 verified, high-confidence nodes is more valuable than one with 10,000 unverified nodes. The Learning Engine enforces minimum confidence thresholds before promotion.

**M-P5: Never hallucinate memory.** An agent that cannot find relevant memory must say so and proceed without it. An agent that fabricates a memory to fill a context gap is doing serious harm.

**M-P6: Memory access is observable.** Every memory read and write is logged. What the system remembers and what it forgets is auditable.

---

# Part 2 — Memory Hierarchy

---

## 2.1 The Six-Tier Architecture

```
╔══════════════════════════════════════════════════════════════════════╗
║  L0 — SESSION MEMORY                                                ║
║  Scope: One BMA cycle. Destroyed at cycle end.                      ║
║  Backend: Python process memory (deque)                             ║
╚══════════════════════════════════════════════════════════════════════╝
                              ↓ (promoted on cycle end)
╔══════════════════════════════════════════════════════════════════════╗
║  L1 — CONVERSATION MEMORY                                           ║
║  Scope: One user session or workflow. Summarized after session.     ║
║  Backend: SQLite (episodic_memory table)                            ║
╚══════════════════════════════════════════════════════════════════════╝
                              ↓ (promoted by Promotion Engine)
╔══════════════════════════════════════════════════════════════════════╗
║  L2 — SEMANTIC MEMORY                                               ║
║  Scope: Platform lifetime. Patterns extracted from L1.              ║
║  Backend: SQLite (semantic_patterns) + Qdrant vectors (Phase 4)     ║
╚══════════════════════════════════════════════════════════════════════╝
                              ↓ (promoted by Learning Engine)
╔══════════════════════════════════════════════════════════════════════╗
║  L3 — KNOWLEDGE GRAPH                                               ║
║  Scope: Platform lifetime. Entities, relationships, rules.          ║
║  Backend: Neo4j (Phase 4) / SQLite adjacency tables (Phase 1–3)     ║
╚══════════════════════════════════════════════════════════════════════╝
                              ↓ (promoted by CEO Agent, human-verified)
╔══════════════════════════════════════════════════════════════════════╗
║  L4 — ORGANIZATIONAL KNOWLEDGE                                      ║
║  Scope: Company lifetime. Cross-product, cross-team intelligence.   ║
║  Backend: Knowledge Graph (dedicated partition) + Markdown files    ║
╚══════════════════════════════════════════════════════════════════════╝
                              ↓ (archived by retention policy)
╔══════════════════════════════════════════════════════════════════════╗
║  L5 — LONG-TERM ARCHIVE                                             ║
║  Scope: Permanent. Raw records that may not expire.                 ║
║  Backend: Cloudflare R2 (compressed JSON) + SQLite index            ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## 2.2 Tier Specification Table

| Property | L0 Session | L1 Conversation | L2 Semantic | L3 Knowledge Graph | L4 Organizational | L5 Archive |
|----------|-----------|----------------|------------|-------------------|-------------------|-----------|
| **Lifetime** | One cycle | One session | Configurable (default: 1 year) | Permanent unless superseded | Permanent | Permanent |
| **Size limit** | 20 entries (deque) | 10,000 entries/product | 100,000 patterns | 1M nodes / 10M edges | Bounded by human curation | Unbounded (compressed) |
| **Backend** | Python deque | SQLite | SQLite + Qdrant | Neo4j / SQLite adj. | KG partition + files | R2 + SQLite |
| **Write access** | Agent (own only) | Agent (own records) | QA Dept only | Engineering + CEO | CEO + human | Automated archival |
| **Read access** | Agent (own only) | All agents | All agents | All agents | All agents | CEO + Engineering |
| **Promotion to next tier** | Auto on cycle end | Promotion Engine | Learning Engine | CEO Agent + human verify | Manual curation | Never (final) |
| **Expiry policy** | Destroyed at cycle end | 90 days then promote-or-archive | Configurable per pattern | No expiry (superseded, not deleted) | No expiry | No expiry |
| **Context Assembly priority** | 1 (highest) | 3 | 5 | 6 | 7 | 8 (lowest, rare) |

---

## 2.3 L0 — Session Memory (Working Memory)

Working memory is the cognitive scratch pad for a single BMA cycle. It holds the active conversation context and tool outputs from the current cycle only.

```python
class WorkingMemory:
    def __init__(self, maxlen: int = 20):
        self._entries: deque[WorkingMemoryEntry] = deque(maxlen=maxlen)

    def add(self, entry: WorkingMemoryEntry) -> None:
        self._entries.append(entry)

    def get_all(self) -> list[WorkingMemoryEntry]:
        return list(self._entries)

    def get_last_n(self, n: int) -> list[WorkingMemoryEntry]:
        return list(self._entries)[-n:]

    def token_estimate(self) -> int:
        return sum(len(e.content.split()) * 1.3 for e in self._entries)

    def summary(self) -> str:
        """One-line summary for injection into downstream prompts."""
        if not self._entries:
            return "No prior context in this session."
        return f"{len(self._entries)} messages. Last: '{self._entries[-1].content[:80]}...'"

class WorkingMemoryEntry(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    tool_name: str | None = None
    tool_result: dict | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
```

**Promotion:** At cycle end, the entire working memory sequence is logged to L1 as an `EpisodicEntry`. The raw deque is then destroyed.

---

## 2.4 L1 — Conversation Memory (Episodic Memory)

The complete, timestamped log of every interaction the platform has had — every agent cycle, every tool call outcome, every evaluation result. This is the ground truth of platform history.

```sql
CREATE TABLE episodic_memory (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Context
    agent           TEXT NOT NULL,
    department      TEXT NOT NULL,
    product         TEXT,                -- NULL = platform-level
    user_id         TEXT,                -- NULL = system/autonomous
    session_id      TEXT NOT NULL,

    -- Task
    intent          TEXT NOT NULL,
    goal            TEXT,
    tools_used      TEXT,                -- JSON array

    -- Outcome
    outcome         TEXT NOT NULL,       -- success|failure|partial
    quality_score   REAL,                -- 0.0–1.0
    content         TEXT,                -- Full content or summary
    duration_ms     INTEGER,

    -- Promotion tracking
    promoted        INTEGER DEFAULT 0,   -- 0=pending, 1=promoted, 2=archived
    promoted_at     DATETIME,
    promotion_tier  TEXT,                -- L2|L5
    
    -- Retention
    expires_at      DATETIME,            -- NULL = permanent
    retention_policy TEXT DEFAULT 'standard'  -- standard|permanent|sensitive
);

CREATE INDEX idx_episodic_agent ON episodic_memory(agent);
CREATE INDEX idx_episodic_product ON episodic_memory(product);
CREATE INDEX idx_episodic_intent ON episodic_memory(intent);
CREATE INDEX idx_episodic_created ON episodic_memory(created_at);
CREATE INDEX idx_episodic_promoted ON episodic_memory(promoted);
```

---

## 2.5 L2 — Semantic Memory

Patterns extracted from L1. Not raw events, but compressed, generalized observations about how the platform behaves.

```sql
CREATE TABLE semantic_patterns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Identity
    pattern_key     TEXT NOT NULL,       -- Unique short identifier
    category        TEXT NOT NULL,       -- behavior|preference|performance|error|domain
    scope           TEXT NOT NULL,       -- platform|product|agent|user

    -- Content
    pattern_value   TEXT NOT NULL,       -- The learned pattern (plain text)
    evidence_count  INTEGER DEFAULT 1,   -- How many L1 records support this
    confidence      REAL DEFAULT 0.5,    -- 0.0–1.0
    
    -- Provenance
    source_product  TEXT,
    source_agent    TEXT,
    source_episodic_ids TEXT,            -- JSON array of episodic_memory.id

    -- Promotion
    promoted_to_kg  INTEGER DEFAULT 0,
    promoted_at     DATETIME,
    kg_node_id      TEXT,

    -- Vector (Phase 4)
    embedding_id    TEXT,                -- Qdrant point ID

    -- Retention
    expires_at      DATETIME,
    retention_policy TEXT DEFAULT 'standard'
);

CREATE UNIQUE INDEX idx_semantic_key ON semantic_patterns(pattern_key);
CREATE INDEX idx_semantic_category ON semantic_patterns(category);
CREATE INDEX idx_semantic_confidence ON semantic_patterns(confidence);
```

---

# Part 3 — Knowledge Graph

---

## 3.1 The Knowledge Graph's Role

The Knowledge Graph is the structured, relational representation of everything SaathiAI knows at a platform level. Unlike L1 (event log) and L2 (pattern list), the Knowledge Graph understands **relationships**.

- "IELTS Writing Task 2" is related to "coherence" (as a band criterion)
- "Mr. Yeti" has a persona that includes "warmth", "humor", "teacher"
- "Groq llama-3.3-70b-versatile" has a performance characteristic of "<200ms p95 latency"
- "Content published at 6 PM" has a performance relationship to "40% higher engagement"

These relationships enable reasoning that is impossible from a list of patterns: "What posting time has the best engagement for Mr. Yeti IELTS videos about Writing?" A vector search can find similar questions; only a Knowledge Graph can answer this one by traversal.

---

## 3.2 Node Types

```
NodeType: Entity
    ├── Product (pielts, HCG_POS, HCG_LiveSignal, Travel, MrYeti)
    ├── Agent (ceo_agent, content_agent, ...)
    ├── Tool (research_web, send_telegram, ...)
    ├── LLMProvider (Groq, Claude, Gemini, Grok, Kimi, Ollama)
    ├── User (operator, pielts_student)
    ├── ContentPiece (video, post, script, blog)
    ├── Persona (MrYeti_persona, BaadarVoice_persona)
    └── Skill (ielts_writing, ielts_speaking, ...)

NodeType: Concept
    ├── Domain (IELTS, canteen_management, travel_booking)
    ├── Topic (band_7_writing, task_2_structure, ...)
    ├── Platform Rule (engineering_rule, content_rule, calibration)
    ├── Pattern (semantic pattern graduated to KG)
    └── Capability (CAP-001 through CAP-031)

NodeType: Event (time-bound, immutable)
    ├── ContentPublished
    ├── EvaluationCompleted
    ├── JobExecuted
    └── IncidentOccurred

NodeType: Metric
    ├── PerformanceMetric (latency_ms, success_rate, ...)
    └── BusinessMetric (engagement_rate, views, conversions, ...)
```

---

## 3.3 Relationship Types

```
Entity → Entity:
    OWNS              (Product OWNS Capability)
    USES              (Agent USES Tool)
    ROUTES_TO         (Department ROUTES_TO Agent)
    DEPENDS_ON        (Agent DEPENDS_ON LLMProvider)
    CREATED           (Agent CREATED ContentPiece)
    EMBODIES          (ContentPiece EMBODIES Persona)

Entity → Concept:
    IMPLEMENTS        (Agent IMPLEMENTS Capability)
    APPLIES_TO        (PlatformRule APPLIES_TO Tool)
    BELONGS_TO        (Skill BELONGS_TO Domain)
    EVALUATED_BY      (Skill EVALUATED_BY Rubric)

Entity → Metric:
    MEASURED_BY       (LLMProvider MEASURED_BY PerformanceMetric)
    ACHIEVED          (ContentPiece ACHIEVED BusinessMetric)
    GOVERNS           (PlatformRule GOVERNS Metric)

Concept → Concept:
    REQUIRES          (band_7 REQUIRES coherence AND range AND accuracy)
    PRECEDES          (research PRECEDES content_generation)
    IMPROVES          (question_hook IMPROVES retention_rate)
    SUPERSEDES        (PlatformRule_v2 SUPERSEDES PlatformRule_v1)
    DERIVED_FROM      (Pattern DERIVED_FROM EpisodicEntry)
```

---

## 3.4 Cypher Conventions

All Knowledge Graph queries are written in Cypher. Conventions that apply to every query in the platform:

**Node labels use PascalCase:**
```cypher
(:Agent), (:ContentPiece), (:PlatformRule)
```

**Relationship types use SCREAMING_SNAKE_CASE:**
```cypher
[:USES], [:DERIVED_FROM], [:MEASURED_BY]
```

**Properties use snake_case:**
```cypher
{ name: "content_agent", version: "1.0.0", created_at: "2026-07-02" }
```

**All nodes have:**
```cypher
{ id: "<uuid>", created_at: "<ISO-8601>", updated_at: "<ISO-8601>", confidence: 0.0-1.0 }
```

**Standard query patterns:**

```cypher
-- Find what an agent is allowed to use
MATCH (a:Agent {name: $agent_name})-[:USES]->(t:Tool)
RETURN t.name, t.safety_level ORDER BY t.safety_level

-- Find all rules that apply to a specific context
MATCH (r:PlatformRule)-[:APPLIES_TO]->(context)
WHERE context.name = $context_name AND r.confidence >= 0.8
RETURN r.rule_text, r.confidence ORDER BY r.confidence DESC

-- Find what knowledge exists about a topic
MATCH (topic:Topic {name: $topic_name})<-[:BELONGS_TO]-(s:Skill)
      -[:EVALUATED_BY]->(rubric)
RETURN topic, s, rubric

-- Trace the provenance of a platform rule
MATCH (rule:PlatformRule)<-[:DERIVED_FROM*]-(source)
WHERE rule.id = $rule_id
RETURN rule, collect(source) as evidence_chain

-- Find patterns that improved a metric
MATCH (p:Pattern)-[:IMPROVES]->(m:Metric {name: $metric_name})
WHERE p.confidence >= 0.8
RETURN p.pattern_text, p.evidence_count
ORDER BY p.evidence_count DESC
```

---

## 3.5 Phase 1–3: SQLite Knowledge Graph (Adjacency Tables)

Before Neo4j is available (Phase 4), the Knowledge Graph is implemented as adjacency tables in SQLite. The query interface is identical from the agent's perspective — the backend swaps transparently.

```sql
CREATE TABLE kg_nodes (
    id              TEXT PRIMARY KEY,   -- UUID
    node_type       TEXT NOT NULL,      -- Agent|Tool|Concept|PlatformRule|...
    name            TEXT NOT NULL,
    properties      TEXT NOT NULL,      -- JSON
    confidence      REAL DEFAULT 1.0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    version         INTEGER DEFAULT 1
);

CREATE TABLE kg_edges (
    id              TEXT PRIMARY KEY,
    from_node_id    TEXT NOT NULL REFERENCES kg_nodes(id),
    to_node_id      TEXT NOT NULL REFERENCES kg_nodes(id),
    relationship    TEXT NOT NULL,
    properties      TEXT,              -- JSON
    confidence      REAL DEFAULT 1.0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    version         INTEGER DEFAULT 1
);

CREATE INDEX idx_kg_edges_from ON kg_edges(from_node_id);
CREATE INDEX idx_kg_edges_to ON kg_edges(to_node_id);
CREATE INDEX idx_kg_edges_rel ON kg_edges(relationship);
CREATE INDEX idx_kg_nodes_type ON kg_nodes(node_type);
CREATE INDEX idx_kg_nodes_name ON kg_nodes(name);
```

---

## 3.6 Graph Versioning

Every node and edge is versioned. When a PlatformRule is updated:

1. The old node is **not deleted**. Its `superseded_by` property is set.
2. A new node is created with `version = old_version + 1`.
3. A `SUPERSEDES` edge connects new to old.

This preserves the full history of how platform knowledge evolved. An agent can query "what did the platform believe about X in March 2026?" by filtering on `created_at < '2026-04-01'`.

```python
async def update_platform_rule(
    rule_id: str, new_value: str, reason: str
) -> str:
    old_node = await kg.get_node(rule_id)

    # Create new version
    new_node = await kg.create_node(
        node_type="PlatformRule",
        properties={
            **old_node.properties,
            "rule_text": new_value,
            "version": old_node.version + 1,
            "updated_reason": reason,
        }
    )

    # Link to old version
    await kg.create_edge(
        from_id=new_node.id,
        to_id=old_node.id,
        relationship="SUPERSEDES",
        properties={"reason": reason}
    )

    # Mark old node as superseded
    await kg.update_node(old_node.id, {"superseded_by": new_node.id})

    return new_node.id
```

---

## 3.7 Graph Migrations

As the graph schema evolves (new node types, new relationship types), migrations are applied through a versioned migration script:

```
docs/decisions/graph-migrations/
├── GM-001_initial_schema.cypher
├── GM-002_add_metric_nodes.cypher
├── GM-003_add_platform_rule_confidence.cypher
└── ...
```

Each migration is idempotent — running it twice produces the same result as running it once. Migration history is recorded in a `graph_migrations` table.

---

# Part 4 — Memory Promotion Engine

---

## 4.1 What the Promotion Engine Does

The Memory Promotion Engine runs as a scheduled job (`memory_promotion_daily`) once per day. It scans L1 (Episodic Memory) for records that are ready for promotion, extracts patterns, and writes them to L2 (Semantic Memory). It also scans L2 for patterns that are ready for promotion to L3 (Knowledge Graph).

This is the mechanism by which SaathiAI **learns from experience without retaining unnecessary detail**.

---

## 4.2 The Promotion Ladder

```
Raw BMA cycle events (L0)
        │
        │  Automatic (cycle end)
        ▼
Episodic entry in L1 (every cycle)
        │
        │  Promotion Engine (daily job)
        │  Trigger: episode is 3+ days old AND similar episodes exist
        ▼
Semantic pattern in L2
        │
        │  Learning Engine (Part 8)
        │  Trigger: pattern confidence ≥ 0.8 AND evidence_count ≥ 3
        ▼
Candidate Knowledge in L3 (unverified)
        │
        │  QA Agent evaluation
        │  Trigger: candidate exists AND evaluation not yet run
        ▼
Verified Knowledge in L3
        │
        │  CEO Agent + human sign-off
        │  Trigger: knowledge is cross-product OR safety-relevant
        ▼
Organizational Knowledge in L4
```

---

## 4.3 Promotion Engine Implementation

```python
class MemoryPromotionEngine:
    """Runs daily. Promotes L1 → L2 and L2 → L3 candidate."""

    async def run(self) -> PromotionReport:
        report = PromotionReport(run_at=datetime.utcnow())

        # Phase A: Promote L1 → L2
        eligible_episodes = await self._find_eligible_episodes()
        for episode_group in self._group_by_intent(eligible_episodes):
            pattern = await self._extract_pattern(episode_group)
            if pattern and pattern.confidence >= 0.5:
                await self._write_to_semantic(pattern)
                await self._mark_episodes_promoted(episode_group)
                report.l1_promoted += len(episode_group)
                report.l2_written += 1

        # Phase B: Promote L2 → L3 candidates
        eligible_patterns = await self._find_eligible_patterns()
        for pattern in eligible_patterns:
            if pattern.confidence >= 0.8 and pattern.evidence_count >= 3:
                candidate = await self._create_kg_candidate(pattern)
                report.l2_to_l3_candidates += 1

        # Phase C: Mark expired records
        await self._archive_expired_episodes()
        report.archived = await self._count_archived()

        return report

    async def _find_eligible_episodes(self) -> list[EpisodicEntry]:
        """Episodes > 3 days old, not yet promoted, with similar intent."""
        return await db.query("""
            SELECT * FROM episodic_memory
            WHERE promoted = 0
              AND created_at < datetime('now', '-3 days')
            ORDER BY intent, created_at
        """)

    async def _group_by_intent(
        self, episodes: list[EpisodicEntry]
    ) -> list[list[EpisodicEntry]]:
        groups: dict[str, list[EpisodicEntry]] = {}
        for ep in episodes:
            key = self._normalize_intent(ep.intent)
            groups.setdefault(key, []).append(ep)
        return [g for g in groups.values() if len(g) >= 2]

    async def _extract_pattern(
        self, episodes: list[EpisodicEntry]
    ) -> SemanticPattern | None:
        if not episodes:
            return None

        extraction = await llm.complete(
            prompt=PATTERN_EXTRACTION_PROMPT.format(
                episodes=[e.to_summary() for e in episodes],
                count=len(episodes),
            ),
            model="standard",
            max_tokens=300,
        )

        if not extraction.has_pattern:
            return None

        return SemanticPattern(
            pattern_key=extraction.key,
            category=extraction.category,
            scope=extraction.scope,
            pattern_value=extraction.pattern,
            evidence_count=len(episodes),
            confidence=extraction.confidence,
            source_episodic_ids=[e.id for e in episodes],
        )
```

---

## 4.4 Promotion Decision Rules

| Condition | Action |
|-----------|--------|
| Episode ≥ 3 days old, similar episodes exist (≥2), outcome = success | Extract pattern, promote to L2 |
| Episode ≥ 3 days old, no similar episodes | Move directly to L5 archive after expiry |
| Episode < 3 days old | Leave in L1, evaluate next run |
| Pattern confidence ≥ 0.8 AND evidence_count ≥ 3 | Create L3 candidate |
| Pattern confidence < 0.5 after 30 days with no new evidence | Mark for archival |
| L3 candidate verified by QA Agent | Promote to Verified Knowledge |
| L3 candidate rejected by QA Agent | Return to L2 with `rejected=True` flag |

---

# Part 5 — Context Assembly Engine

---

## 5.1 Why Context Assembly Must Be Deterministic

The quality of an LLM's response is almost entirely determined by the quality of its context. A well-assembled context that includes the right memories, the right constraints, and the right examples produces better outputs than any prompt engineering trick.

But "well-assembled" must be defined precisely. If context assembly is ad hoc — each agent assembles context differently, in different orders, with different priorities — the system's behavior becomes unpredictable. Two agents facing the same task produce radically different results because they assembled different context. Debugging becomes impossible.

The Context Assembly Engine is a deterministic, priority-ordered pipeline that every agent calls before every significant LLM invocation.

---

## 5.2 Assembly Priority Order

```
Priority  Source                        Token Budget    Always Include
─────────────────────────────────────────────────────────────────────
  1       Current task definition        200 tokens      ✓
  2       Active workflow state           100 tokens      If in workflow
  3       L0 Session memory (working)     400 tokens      ✓
  4       Agent system prompt             150 tokens      ✓
  5       User / operator preferences     100 tokens      If available
  6       L1 Episodic (recent, relevant)  300 tokens      Top 3 by relevance
  7       L2 Semantic patterns            200 tokens      Top 5 by confidence
  8       L3 Knowledge Graph              200 tokens      Top 3 relevant nodes
  9       L1 Episodic (older, low-rel)    100 tokens      Fill remaining budget
 10       L5 Archive                       50 tokens      Rarely; explicit request
─────────────────────────────────────────────────────────────────────
  Total budget per call:              ~1,800 tokens (configurable)
```

---

## 5.3 Assembly Engine Implementation

```python
class ContextAssemblyEngine:
    def __init__(self, config: ContextConfig):
        self.config = config

    async def assemble(
        self,
        task: UnderstandResult,
        agent: str,
        workflow_state: WorkflowState | None = None,
    ) -> AssembledContext:
        budget = TokenBudget(total=self.config.total_token_budget)
        layers: list[ContextLayer] = []

        # Priority 1: Current task — always included, no truncation
        layers.append(ContextLayer(
            priority=1,
            source="task",
            content=self._format_task(task),
            tokens=budget.allocate(200, required=True),
        ))

        # Priority 2: Workflow state — if in a workflow
        if workflow_state:
            layers.append(ContextLayer(
                priority=2,
                source="workflow",
                content=self._format_workflow(workflow_state),
                tokens=budget.allocate(100),
            ))

        # Priority 3: Working memory — recent session context
        working = self.memory.working.get_all()
        layers.append(ContextLayer(
            priority=3,
            source="working_memory",
            content=self._format_working_memory(working),
            tokens=budget.allocate(400, required=True),
        ))

        # Priority 4: Agent system prompt
        contract = AGENT_REGISTRY[agent]
        layers.append(ContextLayer(
            priority=4,
            source="system_prompt",
            content=self._format_system_prompt(contract),
            tokens=budget.allocate(150, required=True),
        ))

        # Priority 5: User/operator preferences (from L2 or L3)
        prefs = await self.memory.semantic.get_preferences(agent=agent)
        if prefs:
            layers.append(ContextLayer(
                priority=5,
                source="preferences",
                content=self._format_preferences(prefs),
                tokens=budget.allocate(100),
            ))

        # Priority 6: Relevant episodic memory
        relevant_episodes = await self.memory.episodic.get_relevant(
            intent=task.intent,
            agent=agent,
            limit=3,
            relevance_threshold=0.7,
        )
        if relevant_episodes:
            layers.append(ContextLayer(
                priority=6,
                source="episodic_relevant",
                content=self._format_episodes(relevant_episodes),
                tokens=budget.allocate(300),
            ))

        # Priority 7: Semantic patterns
        patterns = await self.memory.semantic.search(
            query=task.goal,
            top_k=5,
            min_confidence=0.6,
        )
        if patterns:
            layers.append(ContextLayer(
                priority=7,
                source="semantic_patterns",
                content=self._format_patterns(patterns),
                tokens=budget.allocate(200),
            ))

        # Priority 8: Knowledge Graph — relevant nodes
        if budget.remaining > 200:
            kg_nodes = await self.kg.query_relevant(
                task=task,
                limit=3,
            )
            if kg_nodes:
                layers.append(ContextLayer(
                    priority=8,
                    source="knowledge_graph",
                    content=self._format_kg_nodes(kg_nodes),
                    tokens=budget.allocate(200),
                ))

        return AssembledContext(
            layers=layers,
            total_tokens=budget.used,
            agent=agent,
            assembled_at=datetime.utcnow(),
        )
```

---

## 5.4 Context Compression

When the assembled context exceeds the token budget for a specific LLM call, the Context Compression module trims in reverse priority order:

```python
class ContextCompressor:
    async def compress(
        self, context: AssembledContext, target_tokens: int
    ) -> AssembledContext:
        if context.total_tokens <= target_tokens:
            return context

        # Remove lowest-priority layers first
        layers = sorted(context.layers, key=lambda l: l.priority, reverse=True)
        compressed_layers = []
        current_tokens = 0

        for layer in sorted(context.layers, key=lambda l: l.priority):
            if layer.tokens.required:
                compressed_layers.append(layer)
                current_tokens += layer.tokens.used
            elif current_tokens + layer.tokens.used <= target_tokens:
                compressed_layers.append(layer)
                current_tokens += layer.tokens.used

        return AssembledContext(
            layers=compressed_layers,
            total_tokens=current_tokens,
            agent=context.agent,
            compressed=True,
        )
```

---

# Part 6 — Retrieval Pipeline

---

## 6.1 Retrieval Architecture

The retrieval pipeline is invoked during Context Assembly (Part 5) to find relevant memory records from L1 and L2. It is also used directly by research and evaluation agents that need to query memory as part of their task.

```
Query (intent, content, metadata)
        │
        ▼
┌──────────────────────────────────────────┐
│           RETRIEVAL ROUTER               │
│  Decides: keyword? vector? graph? hybrid?│
└──────┬─────────────────────┬────────────-┘
       │                     │
       ▼                     ▼
┌─────────────┐     ┌─────────────────┐
│  KEYWORD    │     │  VECTOR SEARCH  │
│  SEARCH     │     │  (Qdrant/Phase 4│
│  (SQLite    │     │   + embeddings) │
│  FTS5)      │     └────────┬────────┘
└──────┬──────┘              │
       │                     │
       └──────────┬──────────┘
                  │
                  ▼
         ┌────────────────┐
         │  GRAPH TRAVERSAL│
         │  (Neo4j/SQLite) │
         └────────┬───────┘
                  │
                  ▼
         ┌─────────────────┐
         │  RANKER         │
         │  Score + merge  │
         └────────┬────────┘
                  │
                  ▼
         ┌─────────────────┐
         │  COMPRESSOR     │
         │  Fit to budget  │
         └─────────────────┘
```

---

## 6.2 Keyword Search (Phase 1)

Full-text search over episodic memory using SQLite FTS5. Fast, zero-dependency, effective for exact or near-exact matches.

```sql
-- Enable FTS5 on episodic content
CREATE VIRTUAL TABLE episodic_fts USING fts5(
    content,
    intent,
    agent,
    content=episodic_memory,
    content_rowid=id
);

-- Trigger to keep FTS in sync
CREATE TRIGGER episodic_fts_insert AFTER INSERT ON episodic_memory BEGIN
  INSERT INTO episodic_fts(rowid, content, intent, agent)
  VALUES (new.id, new.content, new.intent, new.agent);
END;
```

```python
async def keyword_search(
    query: str, limit: int = 10, filters: dict = None
) -> list[EpisodicEntry]:
    sql = """
        SELECT e.*, bm25(episodic_fts) as rank
        FROM episodic_fts
        JOIN episodic_memory e ON episodic_fts.rowid = e.id
        WHERE episodic_fts MATCH ?
    """
    params = [query]
    if filters:
        for key, value in filters.items():
            sql += f" AND e.{key} = ?"
            params.append(value)
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)
    return await db.query(sql, params)
```

---

## 6.3 Vector Search (Phase 4)

Semantic similarity search using Qdrant. Finds episodic and semantic memory records that are conceptually similar to the query, even when exact keywords differ.

```python
class VectorSearchEngine:
    def __init__(self, qdrant_client: QdrantClient, embedding_model: str):
        self.client = qdrant_client
        self.embedding_model = embedding_model

    async def embed(self, text: str) -> list[float]:
        # Use Groq or local embedding model
        return await llm.embed(text, model=self.embedding_model)

    async def search(
        self,
        query: str,
        collection: str,  # "episodic" or "semantic"
        top_k: int = 10,
        score_threshold: float = 0.7,
        filters: dict = None,
    ) -> list[SearchResult]:
        query_vector = await self.embed(query)

        qdrant_filter = None
        if filters:
            qdrant_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key=key, match=models.MatchValue(value=value)
                    )
                    for key, value in filters.items()
                ]
            )

        results = self.client.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=top_k,
            score_threshold=score_threshold,
            query_filter=qdrant_filter,
        )
        return [SearchResult(id=r.id, score=r.score, payload=r.payload)
                for r in results]
```

**Embedding model selection:**

| Use Case | Model | Dimensions |
|----------|-------|-----------|
| Episodic memory (English text) | `nomic-embed-text` (local Ollama) | 768 |
| Semantic patterns (short text) | `nomic-embed-text` | 768 |
| Multilingual content | `multilingual-e5-small` | 384 |
| Code snippets | `nomic-embed-code` | 768 |

---

## 6.4 Hybrid Retrieval

For most context assembly calls, keyword and vector search are combined with a score-fusion algorithm:

```python
async def hybrid_search(
    query: str, collection: str, top_k: int = 10
) -> list[SearchResult]:
    # Run both searches in parallel
    keyword_results, vector_results = await asyncio.gather(
        keyword_search(query, limit=top_k * 2),
        vector_search.search(query, collection=collection, top_k=top_k * 2),
    )

    # Reciprocal Rank Fusion
    scores: dict[str, float] = {}
    for rank, result in enumerate(keyword_results):
        scores[result.id] = scores.get(result.id, 0) + 1 / (60 + rank + 1)
    for rank, result in enumerate(vector_results):
        scores[result.id] = scores.get(result.id, 0) + 1 / (60 + rank + 1)

    # Sort by fused score and return top_k
    ranked_ids = sorted(scores, key=scores.get, reverse=True)[:top_k]
    return [await db.get_by_id(id) for id in ranked_ids]
```

---

## 6.5 Graph Traversal

Used when the query involves relationships that simple text search cannot capture:

```python
async def graph_traversal_search(
    entity_name: str,
    relationship_types: list[str],
    max_depth: int = 2,
) -> list[KGNode]:
    # Phase 1-3: SQLite adjacency table traversal
    return await db.query("""
        WITH RECURSIVE traversal(node_id, depth) AS (
            SELECT id, 0 FROM kg_nodes WHERE name = ?
            UNION ALL
            SELECT e.to_node_id, t.depth + 1
            FROM kg_edges e
            JOIN traversal t ON e.from_node_id = t.node_id
            WHERE t.depth < ? AND e.relationship IN ({})
        )
        SELECT DISTINCT n.* FROM traversal t
        JOIN kg_nodes n ON n.id = t.node_id
        ORDER BY t.depth
    """.format(",".join("?" * len(relationship_types))),
    [entity_name, max_depth, *relationship_types])
```

---

## 6.6 Ranking and Re-ranking

After retrieval, results are re-ranked by a compound score:

```
Final Score = (0.4 × relevance_score)
            + (0.3 × recency_score)
            + (0.2 × confidence_score)
            + (0.1 × product_match_score)
```

- **relevance_score**: Hybrid retrieval score (0.0–1.0)
- **recency_score**: Decays from 1.0 to 0.0 over 90 days
- **confidence_score**: Pattern/node confidence level
- **product_match_score**: 1.0 if same product as current task, 0.5 if cross-product, 0.0 if unrelated

---

# Part 7 — Memory Governance

---

## 7.1 Governance Principles

**G-1: The operator owns the data.** All memory data stored in SaathiAI belongs to Ajay Chaulagain as the platform operator. No third party has access to memory data. Third-party LLM providers receive prompt text but do not receive memory records directly.

**G-2: Privacy by default.** Memory records that contain personal information about pielts students are stored under `retention_policy: sensitive` and are never used as context for other products.

**G-3: Right to be forgotten.** Any memory record can be deleted on request. Deletion is a CRITICAL action requiring CEO Agent + operator approval (Part 6, SES-002).

**G-4: Auditability.** Every memory operation — read, write, promote, archive, delete — is logged. The audit log is itself memory that cannot be deleted without operator approval.

**G-5: Conflict resolution favors recency.** When two memory records about the same entity contradict each other, the more recent record is treated as authoritative unless confidence scores indicate otherwise.

---

## 7.2 Retention Policy Matrix

| Memory Type | Retention Policy | Default Lifetime | Archive On Expiry |
|-------------|----------------|-----------------|------------------|
| Standard episodic events | `standard` | 90 days | Yes → L5 |
| Evaluation results (pielts) | `sensitive` | 365 days | Yes → L5 (isolated) |
| Voice session transcripts | `sensitive` | 30 days | Delete (not archive) |
| Platform rule events | `permanent` | Permanent | Never expires |
| Error and incident records | `permanent` | Permanent | Never expires |
| Content published (metadata) | `standard` | 365 days | Yes → L5 |
| Scheduled job logs | `operational` | 60 days | Delete (not archive) |
| Working memory | `session` | Session end | Promoted to L1 |
| Security audit log | `permanent` | Permanent | Never expires |

---

## 7.3 Sensitive Data Rules

pielts student data (scores, transcripts, personal information) is subject to additional rules:

1. **Isolated partition.** Sensitive records are stored with `product = 'pielts'` and `retention_policy = 'sensitive'`. Context Assembly never surfaces sensitive records for non-pielts tasks.

2. **No cross-product promotion.** The Memory Promotion Engine never promotes sensitive records to cross-product semantic patterns or the shared Knowledge Graph.

3. **Shorter retention.** Voice session transcripts (which may contain student speech) are deleted, not archived, after 30 days.

4. **Student deletion request.** If a student requests deletion of their data, the Engineering Director agent can execute `delete_student_records(user_id)` which removes all `user_id = student_id` records from episodic memory. This is a CRITICAL action requiring operator approval.

---

## 7.4 Conflict Resolution

When the Knowledge Graph contains conflicting facts:

```python
class ConflictResolver:
    async def resolve(
        self, node_a: KGNode, node_b: KGNode
    ) -> KGNode:
        if node_a.updated_at > node_b.updated_at:
            # More recent — tentatively authoritative
            if node_a.confidence >= node_b.confidence:
                return node_a  # newer AND more confident
            else:
                # Newer but less confident — flag for human review
                await self._flag_conflict(node_a, node_b)
                return node_b  # Keep higher-confidence version
        else:
            return node_b if node_b.confidence >= node_a.confidence else node_a
```

Flagged conflicts appear in the CEO Morning Dashboard and are resolved by the operator.

---

## 7.5 Memory Audit Log

```sql
CREATE TABLE memory_audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    operation   TEXT NOT NULL,     -- read|write|promote|archive|delete|search
    tier        TEXT NOT NULL,     -- L0|L1|L2|L3|L4|L5
    record_id   TEXT,
    agent       TEXT NOT NULL,
    product     TEXT,
    outcome     TEXT NOT NULL,     -- success|denied|error
    reason      TEXT,
    duration_ms INTEGER
);
```

All operations at L3 and above are logged at `AuditLevel.FULL`. L1 and L2 operations are logged at `AuditLevel.SUMMARY`.

---

# Part 8 — Learning Engine

---

## 8.1 What the Learning Engine Does

The Memory Promotion Engine (Part 4) extracts patterns from episodic history. The Learning Engine takes those patterns and determines which ones are ready to become durable platform knowledge — facts, rules, and capabilities that govern all future behavior.

The Learning Engine closes the loop. Without it, the platform accumulates patterns but never acts on them. With it, observations become improvements.

---

## 8.2 The Learning Cycle

```
Observation (L1 episodic record)
        │
        │  Promotion Engine: extract pattern (Part 4)
        ▼
Candidate Pattern (L2 semantic memory)
        │
        │  Learning Engine Phase 1: evaluate
        ▼
Evaluated Pattern (confidence score, evidence count updated)
        │
        │  Learning Engine Phase 2: knowledge extraction
        │  Trigger: confidence ≥ 0.8, evidence_count ≥ 3
        ▼
Candidate Knowledge (L3 unverified node)
        │
        │  Learning Engine Phase 3: validation
        │  QA Agent reviews with a structured rubric
        ▼
Validated Knowledge (L3 verified node, confidence = 1.0)
        │
        │  Learning Engine Phase 4: graph update
        ▼
Platform Knowledge (connected to relevant KG entities)
        │
        │  Learning Engine Phase 5: capability update
        │  Does this change how an agent should behave?
        ▼
Updated Agent Behavior (prompt update, tool parameter change,
        routing rule update, or contract amendment)
```

---

## 8.3 Learning Engine Implementation

```python
class LearningEngine:
    """Scheduled job: runs after Memory Promotion Engine each day."""

    async def run(self) -> LearningReport:
        report = LearningReport(run_at=datetime.utcnow())

        # Phase 1: Evaluate new patterns
        new_patterns = await self.memory.semantic.get_unevaluated()
        for pattern in new_patterns:
            updated = await self._evaluate_pattern(pattern)
            await self.memory.semantic.update(updated)
            report.patterns_evaluated += 1

        # Phase 2: Promote high-confidence patterns to KG candidates
        ready_patterns = await self.memory.semantic.get_ready_for_promotion()
        for pattern in ready_patterns:
            candidate = await self._extract_knowledge(pattern)
            await self.kg.create_candidate(candidate)
            report.candidates_created += 1

        # Phase 3: Validate candidates with QA Agent
        candidates = await self.kg.get_unvalidated_candidates()
        for candidate in candidates:
            validation = await self._validate_with_qa(candidate)
            if validation.approved:
                await self.kg.promote_to_verified(candidate, validation)
                report.knowledge_verified += 1
            else:
                await self.kg.reject_candidate(candidate, validation.reason)
                report.candidates_rejected += 1

        # Phase 4: Update graph relationships
        verified = await self.kg.get_newly_verified()
        for knowledge in verified:
            await self._update_graph_relationships(knowledge)
            report.graph_updated += 1

        # Phase 5: Trigger capability updates
        actionable = [k for k in verified if k.requires_behavior_change]
        for knowledge in actionable:
            await self._propose_capability_update(knowledge)
            report.capability_updates_proposed += 1

        return report

    async def _evaluate_pattern(
        self, pattern: SemanticPattern
    ) -> SemanticPattern:
        # Find all L1 records that match this pattern
        matching = await self.memory.episodic.find_matching(pattern.pattern_key)
        successes = [m for m in matching if m.outcome == "success"]

        new_confidence = len(successes) / max(len(matching), 1)
        return pattern.model_copy(update={
            "evidence_count": len(matching),
            "confidence": new_confidence,
            "updated_at": datetime.utcnow(),
        })

    async def _validate_with_qa(
        self, candidate: KGCandidate
    ) -> ValidationResult:
        # Route to QA Department Director
        return await platform_client.post(
            "/api/v1/eval/knowledge/validate",
            json={
                "candidate": candidate.model_dump(),
                "evidence": await self._gather_evidence(candidate),
                "rubric": "platform_knowledge_validation",
            }
        )
```

---

## 8.4 QA Validation Rubric for Knowledge Candidates

Before any candidate enters the verified Knowledge Graph, the QA Agent evaluates it against:

| Criterion | Weight | Threshold |
|-----------|--------|-----------|
| **Specificity** — is it concrete, not vague? | 20% | ≥ 0.7 |
| **Generalizability** — applies beyond one context? | 20% | ≥ 0.6 |
| **Evidence quality** — are the supporting episodes high-confidence? | 25% | ≥ 0.75 |
| **Non-contradiction** — consistent with existing KG? | 25% | ≥ 0.9 |
| **Actionability** — can it change agent behavior? | 10% | ≥ 0.5 |

A candidate must pass with a weighted average ≥ 0.72 to become verified knowledge.

---

## 8.5 Capability Update Protocol

When the Learning Engine determines that a verified knowledge node requires a behavior change, it creates a `CapabilityUpdateProposal`:

```python
class CapabilityUpdateProposal(BaseModel):
    knowledge_node_id: str
    affected_agents: list[str]
    change_type: Literal[
        "prompt_update",
        "tool_parameter_change",
        "routing_rule_update",
        "contract_amendment",
        "new_platform_rule",
    ]
    proposed_change: str
    justification: str
    risk_level: SafetyLevel
    requires_human_review: bool
```

All `CapabilityUpdateProposal` items appear in the CEO Morning Dashboard. The operator reviews and approves changes before they are applied. This is the final gate ensuring that the platform learns in a controlled, operator-visible way.

---

# Part 9 — Cross-Product Knowledge

---

## 9.1 The Shared Knowledge Challenge

SaathiAI runs five products. Each product generates operational experience. The challenge is extracting the parts of that experience that are genuinely useful across products — without polluting product-specific memory with irrelevant data from other products.

The principle is **knowledge flows up, specifics stay down:**

```
Product-specific experience (pielts session)
        │
        │  Promotion: extract generalizable patterns only
        ▼
Platform pattern (L2, scope=platform)
        │
        │  Learning Engine: verify and generalize
        ▼
Platform knowledge (L3, no product tag)
        │
        │  Available to all products via Context Assembly
        ▼
Improved behavior in all products
```

---

## 9.2 Knowledge Scope Classification

Every memory record and KG node has a `scope` field:

| Scope | Meaning | Cross-product access |
|-------|---------|---------------------|
| `session` | Current BMA cycle only | No |
| `product:<name>` | Specific to one product | No (sensitive boundary) |
| `department:<name>` | Relevant to agents in a department | No |
| `platform` | Relevant to all products and agents | Yes |

The Promotion Engine only creates `scope: platform` patterns when the extracted insight is genuinely product-agnostic. Product-specific insights stay at `scope: product:<name>`.

---

## 9.3 Cross-Product Knowledge Examples

| Origin Product | Observation | Promoted Knowledge (Platform) |
|---------------|------------|------------------------------|
| pielts | "Users who practice speaking 3× per week show 0.5-band improvement within 4 weeks" | `DOMAIN: intensive_practice_shows_measurable_improvement_in_4_weeks` |
| HCG POS | "Sales reporting is most accurate when inventory is reconciled before daily close, not after" | `WORKFLOW: reconcile_inventory_before_report_generation` |
| Mr. Yeti / Baadar | "Videos with a hook question in the first 3 seconds have 2× completion rate" | `CONTENT_RULE: hook_placement_improves_completion` |
| pielts + HCG | "OmniVoice achieves < 60ms TTS latency for text < 100 words; degrades linearly above 200 words" | `CALIBRATION: omnivoice_latency_model = {tokens_per_ms: 0.3}` |
| All products | "Groq rate limits at 30k tokens/minute; burst limit hit on concurrent requests" | `ENGINEERING_RULE: groq_rate_limit_burst_mitigation = queue_concurrent_requests` |

---

## 9.4 Knowledge Firewall for Sensitive Scopes

Products that handle personal data (pielts student scores and transcripts) must never have their specific data promoted to platform scope:

```python
class PromotionFirewall:
    FIREWALL_PRODUCT_SCOPES = {"pielts_student_data", "user_pii"}

    def check(self, pattern: SemanticPattern) -> bool:
        """Returns True if this pattern is safe to promote to platform scope."""
        if pattern.scope in self.FIREWALL_PRODUCT_SCOPES:
            return False  # Never promote sensitive data
        if any(id in pattern.source_episodic_ids
               for id in self._sensitive_episode_ids()):
            return False  # Pattern derived from sensitive episodes
        return True
```

---

## 9.5 Voice OS Knowledge is Universally Shared

Voice OS improvements are an exception to the "stay in product" default. Because Voice OS is a platform service used by all products, calibration knowledge about STT accuracy, TTS latency, and voice clone performance is always `scope: platform`:

| Voice Knowledge | Scope | Beneficiaries |
|----------------|-------|--------------|
| "Whisper medium achieves 95% accuracy for Nepali-accented English" | platform | pielts, Travel, any future voice product |
| "OmniVoice speaker MrYeti-v2 achieves consistent intonation" | platform | Mr. Yeti, any content pipeline |
| "STT accuracy degrades below 3dB SNR; minimum mic quality requirement" | platform | All voice products |

---

# Part 10 — Future Memory

---

## 10.1 Multi-User Organizations

Today SaathiAI serves one operator (Ajay) and one student population (pielts users). Future versions will serve organizations with multiple operators, multiple team members, and multiple permission levels.

**Required architecture extensions:**

```python
class FutureMemoryConfig(BaseModel):
    # Tenancy
    org_id: str
    user_id: str
    role: Literal["admin", "operator", "member", "viewer"]

    # Memory partitioning
    org_memory_partition: str     # Isolates org's memory from others
    shared_platform_knowledge: bool = True  # Can access platform rules

    # Permission boundaries
    can_read_others_episodic: bool  # False for members by default
    can_write_shared_memory: bool   # Only operators and above
    can_promote_to_knowledge: bool  # Only admins
```

The current single-tenant architecture (one SQLite database, one KG) becomes a multi-tenant architecture where each organization has its own L1 and L2 partition, and shares the L3/L4 platform knowledge.

---

## 10.2 Federated Memory

For organizations with data sovereignty requirements (memory must not leave a specific geographic region), SaathiAI's memory architecture is designed to federate:

```
Organization A (Kathmandu)          Organization B (Singapore)
L1/L2: local SQLite               L1/L2: local SQLite
L3: local Neo4j                    L3: local Neo4j
        │                                  │
        │  Federated sync (platform        │
        │  rules only, no PII)             │
        ▼                                  ▼
        ╔═══════════════════════════════════╗
        ║   Federated Platform Knowledge    ║
        ║   (L4 — platform rules only)      ║
        ╚═══════════════════════════════════╝
```

Federated sync publishes anonymized, aggregated platform rules — never episodic records, never user data.

---

## 10.3 Multimodal Memory

The current architecture stores text. Future products — particularly Video Pipeline (SES-006), Character System (SES-007), and Voice OS — require multimodal memory:

| Memory Type | Storage | Retrieval |
|------------|---------|----------|
| Audio clips (voice profiles) | R2 + SQLite metadata | Similarity search on audio embeddings |
| Video frames (character poses) | R2 + SQLite metadata | Clip similarity model |
| Generated image assets | R2 + SQLite metadata | Image embedding similarity |
| Storyboard sketches | R2 + SQLite metadata | Structure similarity |

Multimodal memory follows the same tier hierarchy and governance rules. The retrieval pipeline adds multimodal search backends alongside text search.

**Embedding models for multimodal (Phase 4+):**

| Modality | Model | Backend |
|----------|-------|---------|
| Text | nomic-embed-text | Qdrant |
| Audio | whisper-embedding | Qdrant |
| Image | clip-vit-base-patch32 | Qdrant |
| Video | video-clip | Qdrant |
| Code | nomic-embed-code | Qdrant |

---

## 10.4 Code Knowledge

As SaathiAI implements itself (the Engineering Department writes and reviews code), code-level knowledge becomes a first-class memory type:

```python
class CodeMemoryNode(KGNode):
    node_type: Literal["CodeKnowledge"] = "CodeKnowledge"
    file_path: str
    function_name: str | None
    pattern: str          # "retry_pattern", "provider_abstraction", etc.
    language: str = "python"
    embedding_id: str     # Code embedding in Qdrant
    usage_count: int = 0
    last_seen_at: datetime
```

Code patterns that are used successfully across multiple engineering tasks are promoted to L3 as `CodeKnowledge` nodes. The Engineering Director agent retrieves these before implementing new code — "how did we handle this pattern before?"

---

## 10.5 Workflow History

Every workflow execution is stored as a `WorkflowHistory` record. This enables:
- Debugging failed workflows by replaying the execution
- Learning from successful workflows (which tool sequences worked?)
- Detecting workflow regressions (success rate dropping over time)

```sql
CREATE TABLE workflow_history (
    id              TEXT PRIMARY KEY,  -- UUID
    workflow_type   TEXT NOT NULL,     -- "daily_content", "ielts_eval", etc.
    started_at      DATETIME NOT NULL,
    completed_at    DATETIME,
    status          TEXT NOT NULL,     -- running|success|failure|partial
    steps_total     INTEGER,
    steps_completed INTEGER,
    steps_failed    INTEGER,
    execution_log   TEXT,              -- JSON array of step results
    outcome_summary TEXT,
    quality_score   REAL
);
```

Workflow history is promoted by the Promotion Engine the same as episodic memory. Successful workflow patterns become `WorkflowPattern` nodes in the Knowledge Graph.

---

# Appendix A — Knowledge Evolution Pipeline

---

## A.1 Pipeline Definition

Not every piece of information deserves to become permanent platform knowledge. The Knowledge Evolution Pipeline defines the gates that information must pass through to reach each level of durability.

```
RAW EVENT (ephemeral)
    │  Agent observes an outcome (e.g., "this prompt format worked")
    │  Storage: Working Memory (L0)
    │  Lifetime: current BMA cycle
    │
    ▼
OBSERVATION (persisted but unprocessed)
    │  The BMA cycle ends; working memory is written to episodic log
    │  Storage: Episodic Memory (L1)
    │  Lifetime: 90 days (then promote-or-archive)
    │  Gate: none (all cycle outcomes are logged)
    │
    ▼
CANDIDATE FACT (pattern proposed)
    │  Promotion Engine runs; finds ≥ 2 similar episodes; extracts pattern
    │  Storage: Semantic Memory (L2, confidence < 0.8)
    │  Lifetime: configurable (default 365 days)
    │  Gate: ≥ 2 similar episodes, coherent pattern extractable
    │
    ▼
VERIFIED FACT (pattern confirmed)
    │  Pattern accumulates evidence (≥ 3 episodes, confidence ≥ 0.8)
    │  Storage: Semantic Memory (L2, confidence ≥ 0.8)
    │  Lifetime: 1 year from last evidence update
    │  Gate: confidence ≥ 0.8, evidence_count ≥ 3
    │
    ▼
KNOWLEDGE (KG node, QA-validated)
    │  Learning Engine promotes to L3; QA Agent validates
    │  Storage: Knowledge Graph (L3)
    │  Lifetime: permanent (superseded, not deleted)
    │  Gate: QA validation score ≥ 0.72 across 5 rubric criteria
    │
    ▼
CAPABILITY (behavior changed)
    │  Knowledge leads to a change in agent prompts, routing, or tools
    │  Storage: Updated agent contract, prompt template, or routing rule
    │  Lifetime: permanent (version-controlled in git)
    │  Gate: CEO Agent review + operator approval
    │
    ▼
ENGINEERING RULE (immutable constraint)
    │  Capability is battle-tested across products and confirmed stable
    │  Storage: L4 Organizational Knowledge + SES document update
    │  Lifetime: permanent — part of the spec itself
    │  Gate: Human curation, documented in this SES document series
```

---

## A.2 Pipeline Metrics

Each gate should be measured to understand where information stagnates or where the system is over-promoting:

| Transition | Metric | Healthy Range |
|------------|--------|--------------|
| L0 → L1 | Episodes logged per day | 50–500 |
| L1 → L2 | Pattern extraction rate | 5–15% of episodes |
| L2 confidence update | Average days to ≥ 0.8 | 14–45 days |
| L2 → L3 candidate | Patterns promoted per week | 1–10 |
| L3 candidate → verified | QA approval rate | 60–80% |
| L3 → capability update | Knowledge leading to behavior change | 20–40% |
| Capability → engineering rule | Rules formalized per quarter | 1–5 |

---

## A.3 Anti-Patterns to Avoid

| Anti-Pattern | What Happens | How to Detect |
|-------------|-------------|--------------|
| Premature promotion | Candidate becomes "knowledge" with only 1 observation | `evidence_count < 3` on L3 nodes |
| Stagnant patterns | L2 patterns with no new evidence in 90 days | `updated_at < now - 90 days AND confidence < 0.8` |
| Orphaned candidates | L3 candidates never validated | `tier = 'candidate' AND created_at < now - 14 days` |
| Contradiction accumulation | Conflicting L3 nodes not resolved | `CONFLICT` relationship count > 0 in KG |
| Over-promotion | Too many `ENGINEERING_RULE` nodes for trivial observations | Human review gate |

---

# Acceptance Criteria

| # | Criterion | Verification Method | Priority |
|---|-----------|---------------------|----------|
| AC-001 | Working Memory destroys its deque at cycle end and persists to L1 | Unit test: verify deque.clear() called after log() | Must Have |
| AC-002 | Memory Promotion Engine runs daily and produces a report | Scheduler job test: verify report written to job log | Must Have |
| AC-003 | No cross-agent L1 write (agent writes only own records) | `MemoryAccessGate.check_write()` unit test | Must Have |
| AC-004 | Knowledge candidates require QA validation before promotion | Integration test: bypass QA and verify L3 write fails | Must Have |
| AC-005 | Context Assembly returns layers in priority order | Unit test with mock memory data | Must Have |
| AC-006 | Sensitive pielts records never appear in cross-product context | Integration test: assemble context for Mr. Yeti agent, verify no pielts episodes | Must Have |
| AC-007 | Knowledge Evolution Pipeline metrics are logged after each daily run | Check promotion report table after scheduled job | Should Have |
| AC-008 | Graph versioning: updating a PlatformRule creates a new node and SUPERSEDES edge | Unit test of `update_platform_rule()` | Should Have |

---

# Implementation Checklist

**Phase 1 — Core Memory (SQLite)**
- [ ] Implement `app/memory/working.py` — deque(maxlen=20) with full lifecycle
- [ ] Implement `app/memory/episodic.py` — SQLite with FTS5, access gate, expiry
- [ ] Implement `app/memory/semantic.py` — SQLite patterns, no Qdrant yet
- [ ] Implement `app/db/schema.py` additions for all memory tables (including KG adjacency)
- [ ] Implement `MemoryAccessGate` — enforce all rules from SES-002 Part 7
- [ ] Implement `MemoryPromotionEngine` — daily job, L1→L2 pattern extraction
- [ ] Implement `ContextAssemblyEngine` — all 8 priority layers, token budget
- [ ] Write unit tests for each memory tier and the access gate

**Phase 2 — Knowledge Graph (SQLite adjacency)**
- [ ] Implement `app/memory/knowledge_graph.py` — SQLite adjacency tables
- [ ] Implement `LearningEngine` — pattern evaluation, QA validation, graph update
- [ ] Implement knowledge candidate → verified knowledge workflow
- [ ] Implement `CapabilityUpdateProposal` pipeline
- [ ] Implement CEO Morning Dashboard memory section

**Phase 3 — Governance**
- [ ] Implement memory audit log with all operation types
- [ ] Implement `ConflictResolver` for KG contradictions
- [ ] Implement `PromotionFirewall` for sensitive data scopes
- [ ] Implement student data deletion flow (CRITICAL, requires approval)

**Phase 4 — Vector + Neo4j**
- [ ] Integrate Qdrant for L2 semantic vector search
- [ ] Implement `VectorSearchEngine` with nomic-embed-text
- [ ] Implement hybrid search (keyword + vector + RRF fusion)
- [ ] Migrate KG adjacency tables to Neo4j
- [ ] Implement Cypher query layer

---

# Risks

| # | Risk | Probability | Impact | Mitigation |
|---|------|-------------|--------|------------|
| R-001 | Memory promotion extracts false patterns from limited evidence | Medium | Medium | Minimum evidence_count ≥ 3 before L3 promotion; QA validation gate |
| R-002 | SQLite FTS5 performance degrades as L1 grows beyond 100K records | Medium | High | Implement pagination + index; plan Neo4j + Qdrant migration at 50K records |
| R-003 | Knowledge graph becomes inconsistent if graph migrations fail mid-run | Low | High | Idempotent migrations; transaction-wrapped; test on copy before production |
| R-004 | Sensitive pielts data leaks to platform patterns | Low | Critical | Firewall enforced at write time + daily audit check |

---

# Related Documents

| Document ID | Title | Relationship |
|-------------|-------|-------------|
| SES-002 | Agent System (Part 7) | Memory Access Policy — governed by this document |
| SES-004 | Voice OS | Conversational continuity uses L1 and L2 |
| SES-005 | AI Studio | Asset reuse and creative consistency via L2 and L3 |
| SES-006 | Video Pipeline | Character and storyboard retrieval from KG |
| SES-007 | Character System | Persistent identity stored as multimodal memory |
| SES-009 | Mission Control | Memory governance dashboard and conflict alerts |

---

*End of SES-003 Cognitive Memory Architecture — Version 1.0.0*

*Status: Approved (L3)*

*Next: [`SES-004_VOICE_OS.md`](SES-004_VOICE_OS.md)*
