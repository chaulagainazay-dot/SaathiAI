# OpenJarvis Repository Static Analysis
## Comprehensive Discovery Report for SaathiOS Character Animation Pipeline

**Analysis Date:** July 10, 2026  
**Repository:** https://github.com/open-jarvis/OpenJarvis.git  
**License:** Apache License 2.0  
**Python Version Requirement:** >=3.10,<3.14  
**Development Status:** Alpha (3)

---

## Executive Summary

OpenJarvis is a **research framework for local-first personal AI**, built on five core architectural primitives: Intelligence (model catalog), Engine (inference backends), Agents (agentic logic), Memory (persistent searchable storage), and Learning (trace-driven optimization). The system is designed to run on personal devices with optional cloud fallback, emphasizing energy efficiency, latency constraints, and learnable routing.

**Key findings for SaathiOS integration:**
- Excellent for **REUSE** of agent orchestration, tool system, and memory backends
- Strong **WRAP** candidates: Ollama integration, scheduling system, channels
- **REPLACE** areas: Custom animation-specific agents, voice synthesis coordination
- **IGNORE**: Desktop GUI, benchmarking framework (irrelevant to pipeline)
- **FUTURE** (M5.2+): Learning/trace system, multi-model router training

---

## 1. Repository Metadata

### Basic Information
- **Organization:** Open Jarvis (Stanford SAIL research)
- **Repository Size:** ~750MB (including uv.lock)
- **Active Development:** Yes (commits through July 2026)
- **Contributors:** Cross-institutional (Hazy Research, Stanford Scaling Intelligence Lab)
- **Community:** Discord, GitHub Discussions, X/Twitter (@OpenJarvisAI)

### License Details
- **License Type:** Apache License 2.0 (fully permissive)
- **Copyright:** 2025 The OpenJarvis Authors
- **Restrictions:** None that affect commercial use or bundling
- **Derivative Work Requirements:** Include license notice, document changes
- **Patent Grant:** Explicit, non-revocable (unless licensee sues)

### Dependencies Licensing
All direct Python dependencies are permissive:
- OpenAI SDK (MIT)
- Click (BSD)
- httpx (BSD)
- Anthropic SDK (MIT)
- Google GenAI SDK (Apache 2.0)
- FastAPI (MIT)
- Uvicorn (BSD)
- PostHog (MIT)
- Datasets (Apache 2.0)
- No GPL/AGPL transitive dependencies detected

---

## 2. Architecture Overview

### Five-Primitive Design

```
┌─────────────────────────────────────────────────────────────┐
│                      EventBus (pub/sub)                     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────┐  ┌────────┐  ┌───────┐  ┌────────┐  ┌────────┐│
│  │Intelligence│ Engine  │ Agents  │ Memory   │Learning │
│  │(Models)   │(Backends)│        │(Storage) │(Router) ││
│  └──────────┘  └────────┘  └───────┘  └────────┘  └────────┘│
│         │         │          │          │          │        │
│         └─────────┴──────────┴──────────┴──────────┴────────→│
│                         Traces & Telemetry                    │
└─────────────────────────────────────────────────────────────┘
```

### Registry Pattern (Core Extensibility)
All components use decorator-based runtime discovery:
```python
@EngineRegistry.register("ollama")
class OllamaEngine(InferenceEngine): ...

@AgentRegistry.register("orchestrator")
class OrchestratorAgent(ToolUsingAgent): ...

@MemoryRegistry.register("faiss")
class FAISSBackend(MemoryBackend): ...
```

---

## 3. Core Modules & Responsibilities

### 3.1 Intelligence Primitive
**Location:** `src/openjarvis/intelligence/`

**Purpose:** Model definition, catalog, metadata

**Components:**
- `model_catalog.py` — BUILTIN_MODELS list with parameter count, context length, VRAM, quantization format
- Model discovery — automatically merges models from running engines into ModelRegistry
- Fallback chains — defined per model in config
- Generation defaults — temperature, max_tokens, top_p, repetition_penalty, stop sequences

**Registration:** Models auto-discovered from all healthy engines at runtime

**Integration with SaathiOS:**
- REUSE: Catalog structure for animation model metadata
- Current limitation: Designed for LLMs, not multimodal animation models

### 3.2 Engine Primitive
**Location:** `src/openjarvis/engine/`

**Inference Runtime Backends:**

| Backend | Type | Port | GPU? | Status | Best For |
|---------|------|------|------|--------|----------|
| **Ollama** | Native HTTP API | 11434 | Optional | ✓ Default | Consumer GPUs, Apple Silicon |
| **vLLM** | OpenAI-compat | 8000 | NVIDIA | ✓ | Datacenter A100/H100 |
| **SGLang** | OpenAI-compat | 30000 | NVIDIA | ✓ | Structured generation |
| **llama.cpp** | OpenAI-compat | 8080 | CPU | ✓ | Edge/CPU-only |
| **MLX** | OpenAI-compat | 8080 | Apple Silicon | ✓ | macOS native |
| **LM Studio** | OpenAI-compat | 1234 | Any | ✓ | Desktop GUI |
| **Apple FM** | OpenAI-compat | 8079 | Apple Silicon | ✓ | Foundation models |
| **Cloud** | Provider SDKs | — | No | ✓ | OpenAI, Anthropic, Google |

**Core ABC:**
```python
class InferenceEngine(ABC):
    def generate(messages, *, model, temperature, max_tokens) → Dict
    async def stream(messages, *, model, ...) → AsyncIterator[str]
    def list_models() → List[str]
    def health() → bool
    def prepare(model) → None
```

**Engine Discovery:** Probes all registered backends, returns healthy ones sorted by config preference

**Fallback Strategy:**
1. Try preferred engine (from config)
2. Auto-probe all registered engines for health
3. Sort by user preference, return first healthy
4. Raises EngineConnectionError if none available

**Tool Call Normalization:**
All engines (OpenAI, Anthropic, Google, Ollama) normalized to flat format:
```json
{
    "tool_calls": [
        {"id": "call_abc", "name": "calculator", "arguments": "{...}"}
    ]
}
```

**Integration with SaathiOS:**
- WRAP: Ollama integration (extend for video/animation inference)
- REPLACE: Cloud fallback (SaathiOS uses internal Gemini bridge)
- REUSE: Engine discovery pattern, health checks

### 3.3 Agents Primitive
**Location:** `src/openjarvis/agents/`

**Built-in Agent Types:**

| Agent | Type | Purpose | State | Max Turns |
|-------|------|---------|-------|-----------|
| `simple` | On-demand | Single-turn, no tools | Stateless | 1 |
| `orchestrator` | On-demand | Multi-turn tool loop | Stateless | 10 |
| `native_react` | On-demand | Thought-Action-Observation | Stateless | 10 |
| `native_openhands` | On-demand | CodeAct (Python execution) | Stateless | 10 |
| `rlm` | On-demand | Recursive LM with REPL | Stateful | ∞ |
| `operative` | Continuous | Persistent with state mgmt | Stateful | ∞ |
| `monitor_operative` | Continuous | Long-horizon with memory | Stateful | ∞ |
| `morning_digest` | Scheduled | Daily briefing generation | Stateful | N/A |
| `deep_research` | On-demand | Multi-hop doc research | Stateless | 15 |

**Tool-Using Base:** All except `simple` accept tools and implement `accepts_tools = True`

**Loop Guard:** Prevents infinite loops with `loop_guard.py` (max turns, cycle detection)

**Execution Modes:**
- **function_calling** — Uses OpenAI-format tool definitions
- **structured** — Text-based THOUGHT/TOOL/INPUT/FINAL_ANSWER (SFT-training compatible)

**Agent Context Injection:**
```python
@dataclass
class AgentContext:
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    memory_handle: Optional[MemoryHandle] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
```

**Integration with SaathiOS:**
- REUSE: OrchestratorAgent as base for AnimationCoordinator
- REUSE: Tool system and tool-calling loop
- WRAP: OperativeAgent for persistent animation state
- REPLACE: Custom agents for video generation coordination

### 3.4 Memory Primitive
**Location:** `src/openjarvis/memory/`

**Five Backends Available:**

| Backend | Index Type | Recall | Latency | Dependencies | Best For |
|---------|-----------|--------|---------|---|---|
| **SQLite/FTS5** | Full-text search | Medium | Fast | None | Default, semantic keywords |
| **FAISS** | Dense vectors | High | Medium | sentence-transformers, numpy | Semantic similarity |
| **ColBERTv2** | Late interaction | Very high | Slow | colbert-ai, torch | Reranking-quality |
| **BM25** | TF-IDF sparse | Medium | Fast | rank-bm25 | Term frequency |
| **Hybrid** | RRF fusion | High | Medium | All above | Best of all methods |

**Pipeline:**
1. **Ingest** — file reading, directory walking (with sensitive file filtering)
2. **Chunk** — configurable chunk_size, overlap (default 512/64)
3. **Embed** — optional (FAISS, ColBERT, Hybrid)
4. **Store** — backend persistence
5. **Retrieve** — query-time retrieval with source attribution

**Configuration in config.toml:**
```toml
[tools.storage]
default_backend = "sqlite"      # or "faiss", "colbert", "bm25", "hybrid"
db_path = "~/.openjarvis/memory.db"
chunk_size = 512
chunk_overlap = 64
embedding_model = "all-MiniLM-L6-v2"  # sentence-transformers
```

**Context Injection:**
If `agent.context_from_memory = true`, relevant docs automatically prepended to prompt

**Integration with SaathiOS:**
- REUSE: Hybrid backend for scene/character context retrieval
- WRAP: Chunking pipeline for animation assets (scenes, characters, props)
- REPLACE: Embedding model (use animation-specific embeddings)

### 3.5 Learning & Traces Primitive
**Location:** `src/openjarvis/learning/` and `src/openjarvis/traces/`

**Trace System:**
Every agent interaction produces a `Trace`:
```python
@dataclass
class Trace:
    query: str
    model: str
    agent: str
    steps: List[TraceStep]  # routing, memory retrieval, tool calls, LLM calls
    outcome: str            # "success", "partial", "failure"
    feedback_score: float   # [0.0, 1.0]
    tokens_used: Dict[str, int]
    latency_ms: float
    energy_joules: float
```

**TraceStore:** SQLite persistence at `~/.openjarvis/traces.db`

**TraceAnalyzer:** Aggregates statistics (success rate, avg latency, token usage by model/agent)

**Router Policies:**

1. **Heuristic (default)**
   - Rule-based (6 priority rules)
   - Code detection → prefer "coder"/"code" models
   - Math detection → prefer largest model
   - Query length → small/large model heuristic
   - Urgency override → fastest model if urgency > 0.8
   
2. **Learned (TraceDrivenPolicy)**
   - Learns from historical traces
   - Groups queries by category (code, math, short, long, general)
   - Scores models by: 60% success rate + 40% user feedback
   - Requires min 5 samples per category

3. **SFT/GRPO (future)**
   - Supervised fine-tuning or RL-based routing
   - Structured traces feed training data

**Integration with SaathiOS:**
- REUSE: Trace structure for animation generation metrics
- REUSE: TraceStore for animation quality feedback loop
- FUTURE: Learn optimal agent/model selection for each scene type

---

## 4. Dependencies Analysis

### Direct Python Dependencies

**Core (always installed):**
```
click>=8                         # CLI framework
datasets>=4.5.0                  # HuggingFace data loading
ddgs>=9.11.4                     # DuckDuckGo search (no API key)
httpx>=0.27                      # Async HTTP client
openai>=1.30                     # OpenAI SDK
nvidia-ml-py>=12.560.30          # NVIDIA GPU metrics
posthog>=3.0                     # Analytics (optional in practice)
python-telegram-bot>=22.6        # Telegram channel
rich>=13                         # CLI formatting
tomlkit>=0.12                    # TOML parsing
websockets>=15.0.1               # WebSocket support
```

**Optional Features (extras):**
```toml
inference-mlx = ["mlx-lm>=0.31.1"]                    # Apple Silicon
inference-vllm = ["vllm>=0.16.0"]                     # NVIDIA datacenter
inference-cloud = ["anthropic>=0.30"]                 # Claude, Gemini
inference-google = ["google-genai>=1.0"]              # Google models
inference-litellm = ["litellm>=1.40"]                 # 100+ provider proxy

memory-faiss = ["faiss-cpu", "sentence-transformers", "numpy"]
memory-colbert = ["colbert-ai>=0.2", "torch>=2.0"]
memory-pdf = ["pdfplumber>=0.10"]
memory-bm25 = ["rank-bm25>=0.2.2"]

server = ["fastapi>=0.110", "uvicorn>=0.30", "pydantic>=2.0"]
desktop = [fastapi, uvicorn, pydantic, "faster-whisper>=1.0"]
browser = ["playwright>=1.40"]
speech = ["faster-whisper>=1.0"]
sandbox = ["docker>=7.0"]
scheduler = ["croniter>=2.0"]
```

### System Requirements

**Python:** 3.10–3.13 (3.14 excluded due to numpy wheel gaps on Windows)

**Runtime Services:**
- Ollama (or alternative inference backend)
- Optional: Docker (for sandboxed agents)
- Optional: System tools (git, ffmpeg, playwright browsers)

**Hardware:**
- CPU: Any (ARM, x86, x64)
- RAM: 8GB+ (for Ollama + embeddings)
- GPU: Optional (Ollama auto-detects NVIDIA, AMD, Apple Silicon)
- Storage: 2-50GB (depends on models, memory backends)

### No GPL/AGPL Dependencies
Fully compatible with commercial/proprietary code — no copyleft obligations.

---

## 5. Ollama Integration & Local Model Support

### Ollama Engine Implementation
**File:** `src/openjarvis/engine/ollama.py`

**HTTP API Endpoints Used:**
- `POST /api/chat` — Streaming completion with tools
- `GET /api/tags` — List available models
- Health check: GET /api/tags (used to probe connectivity)

**Configuration:**
```toml
[engine.ollama]
host = "http://localhost:11434"     # OLLAMA_HOST env var override
timeout = 1800.0                    # Token read timeout
num_ctx = 16384                     # Default context window
```

**Context Window:**
- Default: 16384 tokens (override via `JARVIS_NUM_CTX` env var)
- Rationale: Raised above Ollama's 4k default to fit images + conversation

**Tool Support:**
- Passes `tools` in request payload as JSON array
- Extracts `tool_calls` from response
- Handles Qwen3 control tokens (`/think`, `/no_think`) — filtered if sole argument

**Model Discovery:**
Polls `/api/tags` on startup, auto-discovers available models

**Fallback Behavior:**
If Ollama is unavailable, system falls through to next registered engine in health check order

**Integration with SaathiOS:**
- WRAP: Extend OllamaEngine for custom animation inference (Wav2Lip, Runway, etc.)
- REUSE: Health check pattern
- Current: Ollama optimized for LLMs only

### Cloud Fallback Mechanisms

**Architecture:**
```python
def _ensure_engine():
    # 1. Try preferred engine from config
    # 2. If unavailable, probe ALL registered engines in order
    # 3. Return first healthy engine
    # 4. Raise EngineConnectionError if none available
```

**Engine Selection Hierarchy:**
1. Preferred engine from `[intelligence].preferred_engine` in config.toml
2. First healthy engine from probing all registered backends
3. Environment-specific default (Ollama on macOS, vLLM on datacenter)
4. Explicit `engine_key` parameter to Jarvis()

**Cloud Engine (OpenAI, Anthropic, Google):**

**File:** `src/openjarvis/engine/cloud.py`

**Supported Providers:**
- OpenAI (GPT-4o, o3-mini, etc.)
- Anthropic (Claude Sonnet, Opus, Haiku)
- Google (Gemini Pro/Flash)
- MiniMax (Chinese market)
- DeepSeek
- OpenRouter (proxy for 100+ models)
- LiteLLM (unified endpoint to 100+ providers)

**API Key Detection:**
- `OPENAI_API_KEY` → OpenAI models
- `ANTHROPIC_API_KEY` → Claude models
- `GOOGLE_API_KEY` → Gemini models
- Model prefix detection (`gpt-`, `claude-`, `gemini-`)

**Cost Tracking:**
Hardcoded pricing table for input/output tokens (can be updated per-release)

**Retry Strategy:**
- Exponential backoff for rate limits (429)
- Jitter to prevent thundering herd
- Max retries: 3 (configurable)

**Tool Call Normalization:**
Each provider's native format converted to flat OpenAI-compatible format

**Integration with SaathiOS:**
- REUSE: Cloud engine as fallback (when Ollama unavailable)
- WRAP: Add animation-specific cost tracking
- REPLACE: Use internal Gemini bridge (not public API)

---

## 6. Skills System (Reusable Workflows)

**Location:** `src/openjarvis/skills/`

### System Design

```
SkillManager (discovery + orchestration)
    ├── discover(paths) → load manifests
    ├── get_skill_tools() → wrap as BaseTool
    ├── get_catalog_xml() → system prompt injection
    └── get_few_shot_examples() → agent training data
```

### Manifest Format (agentskills.io standard)

**SKILL.md Frontmatter:**
```yaml
---
name: research-and-summarize
version: "1.0.0"
description: "Multi-hop web research with citation tracking"
author: "Your Name"
tags: ["research", "web", "summarization"]
required_capabilities: ["internet_access"]
disable_model_invocation: false  # Can agents call this skill directly?
user_invocable: true             # Can users invoke via CLI?
depends:                          # Skill dependencies (not tool deps)
  - search-arxiv
  - chunk-and-embed
---
```

### Skill Steps (Pipeline)

Each skill contains sequential steps:
```yaml
steps:
  - tool_name: "search_web"
    arguments:
      query: "{search_query}"
      output_key: "search_results"
  
  - tool_name: "chunk_text"
    arguments:
      text: "{search_results.content}"
      chunk_size: 512
      output_key: "chunks"
  
  - skill_name: "summarize_chunks"    # Sub-skill invocation
    arguments:
      chunks: "{chunks}"
      output_key: "summary"
```

### SkillTool Adapter
Wraps any skill as a `BaseTool` so agents can invoke it:
- `spec` property: derives `ToolSpec` from manifest
- `execute()`: runs pipeline, returns result or Markdown content
- Metadata tagging: `{"skill": name, "skill_source": src}`

### Dependency Graph Validation
- Cycle detection (Kahn's algorithm)
- Max depth enforcement (default 5 levels)
- Capability union checking

### Optimization Overlay
Per-skill sidecar at `~/.openjarvis/learning/skills/<name>/optimized.toml`:
```toml
[optimized]
skill_name = "research-and-summarize"
optimizer = "dspy"
description = "Optimized description"

[[optimized.few_shot]]
input = "transformer attention mechanisms"
output = "## Recent Advances..."
```

### Source Resolvers (Import)

| Resolver | Repo Layout | Source |
|----------|------------|--------|
| HermesResolver | `skills/<category>/<skill>/` | Hermes Agent (~150 skills) |
| OpenClawResolver | `skills/<owner>/<skill>/` | OpenClaw (~13,700 community) |
| GitHubResolver | Recursive SKILL.md walk | Any GitHub repo |

### Integration with SaathiOS:**
- WRAP: Animation skills (pose-to-video, character-animator, scene-composer)
- WRAP: Voice + animation sync skills
- REUSE: Dependency graph for animation pipeline DAGs
- FUTURE: Learn optimal skill composition for each character/scene

---

## 7. Scheduling (Cron, Continuous Agents)

**Location:** `src/openjarvis/scheduler/`

**Components:**

1. **TaskScheduler** (`scheduler.py`)
   - Cron scheduling (croniter backend)
   - Interval-based runs
   - One-time execution
   - Background polling (separate thread, no external daemon)

2. **SchedulerStore** (`store.py`)
   - SQLite persistence
   - Run logs with timestamps, status, error messages
   - Task state (active, paused, cancelled)

3. **Preset Agents**
   - `morning_digest` — scheduled daily briefing (email, calendar, health, news)
   - `monitor_operative` — long-running continuous agent with state
   - `operative` — persistent agent with manual run scheduling

**Configuration:**
```toml
[scheduler]
enabled = true
db_path = "~/.openjarvis/scheduler.db"
polling_interval = 60  # seconds between cron evaluations
```

**Example Task Definition:**
```python
scheduler.add_task(
    name="daily_analysis",
    agent_name="monitor_operative",
    cron="0 9 * * *",  # 9 AM daily
    config={
        "query": "Analyze today's news for my interests",
        "max_turns": 10
    }
)
```

**Daemon Modes:**
- **CLI daemon:** `jarvis daemon start` (background process via systemd/launchd)
- **Embedded:** Call `scheduler.run_pending()` from your own event loop
- **No external service required** — SQLite coordination

**Integration with SaathiOS:**
- WRAP: Schedule daily animation generation (e.g., character briefing videos)
- WRAP: Persistent animation state tracking (character mood, story progression)
- REUSE: Run log persistence and monitoring

---

## 8. Agent Types & Orchestration

### BaseAgent ABC
```python
class BaseAgent(ABC):
    def run(self, input: str, context: Optional[AgentContext]) → AgentResult
    
@dataclass
class AgentResult:
    content: str
    usage: Dict[str, int]  # token counts
    tool_results: Optional[List[ToolResult]] = None
    intermediate_steps: Optional[List[Tuple]] = None
```

### Agent Orchestration Flow

```
Jarvis.ask("query")
  ├─→ _resolve_model("query")    # Router selects model
  ├─→ _run_agent(agent_name, ...)
  │   ├─→ AgentRegistry.get(agent_name)
  │   ├─→ agent.run(query, context)
  │   └─→ (Agent-specific loop, e.g. OrchestratorAgent)
  │       └─→ THOUGHT/TOOL/INPUT/FINAL_ANSWER or function_calling
  └─→ Return AgentResult
```

### Multi-Tool Orchestration

**Tool Discovery:** Agent can accept any subset of tools
```python
agent = OrchestratorAgent(
    engine=engine,
    model="qwen3:8b",
    tools=[search_tool, calculator_tool, file_read_tool, think_tool],
    mode="function_calling"  # or "structured"
)
```

**Tool Execution in Loop:**
1. LLM outputs tool_calls: `[{id, name, arguments}]`
2. Agent executes each tool in parallel (if `parallel_tools=True`)
3. Returns `[{tool_name, content, error}]` as ToolResult
4. Appends to messages and loops until LLM stops calling tools

**Structured Mode (SFT/GRPO-compatible):**
Agent uses text-based format:
```
THOUGHT: I need to search for information
TOOL: web_search
INPUT: {"query": "..."}
FINAL_ANSWER: Based on search results...
```

This format is SFT-trainable (feeds training data for future fine-tunes)

### Hybrid Agents (Research Code)
**Location:** `src/openjarvis/agents/hybrid/`

Advanced multi-model orchestration:
- **Orchestrator** — full agentic loop with routing
- **Conductor** — coordinates multiple sub-agents
- **SkillOrchestra** — orchestrates skills (tools) rather than raw tools
- **ToolOrchestra** — advanced tool calling with planning
- **Archon** — high-level agent planning
- **Minions** — sub-agent delegation
- **Mini-SWE Agent** — specialized for software engineering tasks

**Status:** Research/experimental; use SimpleAgent/OrchestratorAgent for production

### Integration with SaathiOS:**
- REUSE: OrchestratorAgent as AnimationCoordinator base
- WRAP: Custom AnimationAgent for video generation tasks
- FUTURE: SkillOrchestra for animation pipeline DAG execution

---

## 9. Benchmarking & Evaluation

**Location:** `src/openjarvis/bench/` and `src/openjarvis/evals/`

### Benchmark Framework

**BaseBenchmark ABC:**
```python
class BaseBenchmark(ABC):
    def run(self, model: str, num_samples: int) → BenchResult
    
@dataclass
class BenchResult:
    name: str
    model: str
    latency_ms: float
    throughput_tokens_per_sec: float
    memory_used_mb: float
```

**Built-in Benchmarks:**
- `LatencyBenchmark` — per-call latency percentiles (p50, p95, p99)
- `ThroughputBenchmark` — tokens/second (streaming)
- `EnergyBenchmark` — GPU/CPU energy consumption (Joules)
- `ToxicityBenchmark` — safety/bias metrics

**CLI Usage:**
```bash
jarvis bench latency --model qwen3:8b --samples 100 --seeds 42
jarvis bench throughput --model llama3.2:3b
```

### Evaluation System

**Scorer Types:**
- Exact match, F1, BLEU (text tasks)
- Toxicity, bias, fairness (safety)
- Custom scorers via plugin interface

**Dataset Sources:**
- HuggingFace Datasets Hub (auto-download)
- Local file ingest
- Benchmark suites (HELM, LiveBench, etc.)

**Evaluation Loop:**
```
jarvis eval <benchmark> --model <model> --scorer <scorer> --seeds 42
```

**Integration with SaathiOS:**
- IGNORE: Not applicable to character animation pipeline
- FUTURE: Custom benchmarks for animation quality metrics

---

## 10. Tracing & Observability

**Location:** `src/openjarvis/traces/` and `src/openjarvis/telemetry/`

### Trace System

**Collector:** Wraps any agent and records full interaction
```python
collector = TraceCollector(agent, trace_store)
result = collector.run("query")
# Automatically persists Trace to SQLite
```

**Trace Data:**
```python
@dataclass
class Trace:
    query: str
    model: str
    agent: str
    engine: str
    steps: List[TraceStep]
        # Each step: timestamp, type (routing|memory|tool|llm), result
    outcome: str  # "success", "partial", "failure"
    tokens: Dict[str, int]
    latency_ms: float
    energy_joules: Optional[float]
```

**TraceStore:** SQLite at `~/.openjarvis/traces.db`

**TraceAnalyzer:** Aggregates statistics
```python
analyzer = TraceAnalyzer(store)
stats = analyzer.get_stats_by_model()
# Returns: {model: {avg_latency, success_rate, avg_tokens, ...}}
```

### Telemetry System

**Location:** `src/openjarvis/telemetry/`

**InstrumentedEngine:** Wraps any engine to record:
- Prompt/completion tokens
- Latency (per-call, cumulative)
- Energy (GPU/CPU power consumption)
- Model, engine, routing decision

**Energy Monitor:**
- NVIDIA GPUs: `nvidia-ml-py` (NVIDIA Management Library)
- AMD GPUs: `amdsmi` (ROCm SMI)
- Apple Silicon: `zeus-ml[apple]`
- CPU: Built-in energy estimation

**TelemetryStore:** SQLite persistence
```
timestamp | model | engine | prompt_tokens | completion_tokens | latency_ms | energy_joules
```

**PostHog Integration:** Optional analytics endpoint (privacy-conscious)

### EventBus (Pub/Sub)

Central event system:
```python
@dataclass
class Event:
    type: EventType  # TOOL_CALL_START, SECURITY_ALERT, etc.
    payload: Dict[str, Any]
    timestamp: float
```

**Event Types:**
- Agent execution: `AGENT_RUN_START`, `AGENT_RUN_END`
- Tool calls: `TOOL_CALL_START`, `TOOL_CALL_END`
- Memory: `MEMORY_RETRIEVE`, `MEMORY_STORE`
- Security: `SECURITY_ALERT`, `SECURITY_BLOCK`
- Skill: `SKILL_EXECUTE_START`, `SKILL_EXECUTE_END`

**Subscribers:** TraceCollector, TelemetryStore, AuditLogger all subscribe

**Integration with SaathiOS:**
- REUSE: TraceStore for animation quality feedback
- REUSE: EventBus for pipeline orchestration events
- REUSE: Energy monitoring for video generation cost tracking
- WRAP: Custom events for animation-specific metrics

---

## 11. Security Model

**Location:** `src/openjarvis/security/`

### Scanner Pipeline

**BaseScanner ABC:**
```python
class BaseScanner(ABC):
    def scan(text: str) → ScanResult
    def redact(text: str, result: ScanResult) → str
```

**Built-in Scanners:**
- `SecretScanner` — API keys, tokens, credentials (regex patterns)
- `PIIScanner` — PII: emails, phone numbers, SSNs, credit cards

**Redaction Modes:**
1. **WARN** — Log finding, return text unchanged
2. **REDACT** — Replace sensitive values, return sanitized text
3. **BLOCK** — Raise SecurityBlockError, prevent execution

### GuardrailsEngine Wrapper

Decorator pattern wraps any InferenceEngine:
```python
engine = OllamaEngine(host="http://localhost:11434")
guarded = GuardrailsEngine(
    engine=engine,
    scanners=[SecretScanner(), PIIScanner()],
    mode=RedactionMode.REDACT
)
```

**Scanning Occurs:**
- **Input:** Before sending to engine (can BLOCK)
- **Output:** After engine response (WARN/REDACT only, can't prevent streaming tokens)

### File Policy

**is_sensitive_file()** — Blocks reading:
- `.env`, `.aws`, `.ssh` (credential files)
- `*.pem`, `*.key` (private keys)
- Config files in home dir
- Configurable patterns in `file_policy.py`

**FileReadTool Integration:** Always checks before reading

**Memory Ingest:** Silently skips sensitive files

### Audit Logger

**AuditLogger:** Subscribes to security events, persists to SQLite
```
~/.openjarvis/audit.db
  security_events table:
    - timestamp
    - event_type (ALERT, BLOCK)
    - findings_json (list of ScanFinding)
    - content_preview (first 100 chars)
    - action_taken (warn, redact, block)
```

### Capability Policy

**Role-based access control (RBAC):**
- Agents can declare required capabilities (e.g., `shell_exec`, `file_write`)
- Policy enforces: who can use what tools
- Configurable in `[security.capabilities]` in config.toml

### Sandbox (Container Isolation)

**SandboxedAgent:** Runs any agent in Docker/Podman container
```python
agent = SandboxedAgent(
    agent=OrchestratorAgent(...),
    engine="docker",  # or "podman"
    mount_allowlist=[("/home/user/data", "ro")],  # read-only
    max_memory_mb=2048
)
```

**Mount Security:** Validates all mounts against allowlist before starting container

**Integration with SaathiOS:**
- WRAP: GuardrailsEngine for prompt injection prevention
- REUSE: Audit logging for animation generation audit trail
- WRAP: Sandbox for untrusted code execution (character behavior scripts)

---

## 12. Licensing & Dependency Audit

### Direct Dependency Licenses

| Package | License | Type | Risk |
|---------|---------|------|------|
| click | BSD | Permissive | None |
| datasets | Apache 2.0 | Permissive | None |
| ddgs | MIT | Permissive | None |
| httpx | BSD | Permissive | None |
| openai | MIT | Permissive | None |
| anthropic | MIT | Permissive | None |
| google-genai | Apache 2.0 | Permissive | None |
| fastapi | MIT | Permissive | None |
| uvicorn | BSD | Permissive | None |
| pydantic | MIT | Permissive | None |
| pytorch (optional) | BSD | Permissive | None |
| transformers (optional) | Apache 2.0 | Permissive | None |

**No GPL, AGPL, or Copyleft:** All dependencies are permissive

### Transitive Dependencies
Checked via `pip-audit` (no known critical vulnerabilities as of July 2026)

### License Compliance for Distribution

If bundling OpenJarvis in SaathiOS:
1. ✓ Include Apache 2.0 license file
2. ✓ Document all direct dependencies (output from `pip freeze`)
3. ✓ Include NOTICE file with attribution
4. ✓ No additional restrictions on your commercial use

---

## 13. Runtime Assumptions & Requirements

### Hardware Minimum
- CPU: Dual-core (ARM or x86)
- RAM: 8GB (4GB minimum if no embeddings)
- GPU: Optional (NVIDIA, AMD, Apple Silicon auto-detected)
- Storage: 2GB (base install) + model size

### Inference Runtime

**Exactly one of:**
1. Ollama (`ollama serve` running locally)
2. vLLM (`vllm serve` on NVIDIA GPU)
3. SGLang (`sglang launch` on NVIDIA GPU)
4. llama.cpp (local CPU/GPU binary)
5. MLX (Apple Silicon native)
6. LM Studio (desktop GUI)
7. Cloud API (OpenAI, Anthropic, Google)

**Probing Strategy:**
- On startup, `discover_engines()` tries health checks for all registered backends
- Returns sorted list of healthy engines
- First healthy engine used unless `preferred_engine` specified

### Network Assumptions

**Optional (feature-gated):**
- Internet access for search tools, API calls
- Cloud API endpoints (if using cloud fallback)
- PostHog telemetry (can be disabled)
- GitHub/HuggingFace for skill/model downloads

**Always Local First:** If Ollama running, cloud only used if Ollama unavailable

### Process Isolation

**No external service required** — everything runs in-process:
- Scheduler uses background thread (no systemd daemon needed)
- Memory backend uses SQLite (no Redis/Postgres)
- Traces stored locally (no remote analytics)

Optional:
- Docker/Podman for sandboxed agent execution
- Git for version control (skills, models)

### Configuration Load Order

```
1. ~/.openjarvis/config.toml (user custom)
2. XDG_CONFIG_HOME/openjarvis/config.toml (Linux standard)
3. ~/.openjarvis/config.local.toml (local overrides, gitignored)
4. Built-in defaults from JarvisConfig dataclass
```

Environment variables override config file values:
- `OLLAMA_HOST` → engine.ollama.host
- `OPENAI_API_KEY` → cloud engine activation
- `JARVIS_NUM_CTX` → Ollama context window
- `DEBUG` → logging level

---

## 14. Classification for SaathiOS Character Animation Pipeline

### REUSE (Direct Integration)

**High-Confidence Reuse:**
1. **OrchestratorAgent** as base for AnimationCoordinator
   - Multi-turn tool loop for animation generation workflow
   - Tool calling + streaming response handling
   - Proven for multi-step reasoning (code, research)

2. **Tool System** (BaseTool, ToolSpec, ToolExecutor)
   - Interface for animation tools (character-generator, scene-composer, voice-sync)
   - Parallel tool execution
   - Error handling and result serialization

3. **Memory Backends** (Hybrid FAISS + BM25)
   - Scene library indexing (character poses, props, environments)
   - Fast semantic search for asset lookup
   - Context injection for animation parameters

4. **TraceStore & TraceAnalyzer**
   - Quality feedback loop for animation generation
   - Track which models/agents produce best videos per scene type
   - Cost/latency metrics for video generation

5. **EventBus (Pub/Sub)**
   - Pipeline orchestration (trigger animation steps in sequence)
   - Monitoring and alerting for long-running video jobs
   - Integration with external systems (Telegram alerts, dashboards)

6. **Skills System** (SkillManager, SkillTool, dependency graph)
   - Reusable animation workflows (pose-to-video, character-sync, scene-compose)
   - Skill composition for complex videos (multi-character, multi-scene)
   - Optimization overlays for skill parameter tuning

7. **TaskScheduler**
   - Daily/hourly animation generation (briefing videos, content calendar)
   - Persistent state for long-running animations
   - Run log tracking

**Medium-Confidence Reuse:**
8. **Security Guardrails** (GuardrailsEngine wrapper)
   - Prevent injection attacks in animation prompts
   - Audit logging for animation generation

---

### WRAP (Needs Adapter)

**High-Confidence Wrapping:**
1. **OllamaEngine**
   - Extend to support multi-modal endpoints (Wav2Lip, Runway, ComfyUI)
   - Add custom payload formatting for animation models
   - Pool management for video inference (long-running, resource-intensive)

2. **Scheduler** (background task management)
   - Add animation-specific job states (queued, rendering, encoding)
   - Integration with render farm load balancing
   - Webhook callbacks for downstream processing

3. **Channels** (messaging integration)
   - Extend existing Telegram channel for animation delivery
   - Add Discord for team collaboration
   - Custom webhook for CI/CD integration (trigger on build events)

4. **HybridSearch** (memory retrieval)
   - Adapt chunking for animation keyframes/poses (not text)
   - Custom embedding model for animation asset similarity
   - Re-ranker for pose/motion relevance

**Medium-Confidence Wrapping:**
5. **Learning/Router** (model selection)
   - Extend heuristic router for animation scene classification
   - Learn which model (Runway vs. ComfyUI) best suits each scene type
   - Cost-aware routing (minimize inference spend per scene)

6. **Telemetry** (energy/latency monitoring)
   - Extend energy monitor for GPU memory + time-to-video metrics
   - Track render farm node health and capacity

---

### REPLACE (Custom Build)

**Must Replace:**
1. **Intelligence.model_catalog** — Animation models, not LLMs
   - Custom metadata: resolution, fps, character count, duration
   - Quantization irrelevant (animation models use different optimization)

2. **Cloud Fallback** — Use internal Gemini bridge, not public APIs
   - Cost control (unlimited budget unavailable)
   - Latency SLAs for real-time animation

3. **Agent Types** — AnimationCoordinator, CharacterAnimator, SceneComposer
   - Animation-specific state (character poses, lighting, camera)
   - Custom loop logic (render + post-process, not LLM chain)

4. **Voice/Audio Integration** — Bespoke voice sync
   - Faster-Whisper for speech-to-text
   - Custom lip-sync via OmniVoice or Wav2Lip
   - NOT generic speech channel

5. **Sandbox** — Animation-specific containerization
   - ComfyUI workflow isolation
   - Resource limits (GPU memory, frame rate)
   - NOT generic Docker wrapper

---

### IGNORE (Not Useful)

1. **Desktop GUI** (`src/openjarvis/desktop/`) — Tauri-based UI
   - SaathiOS has custom web frontend
   - No value in porting

2. **Benchmarking Framework** (`src/openjarvis/bench/`)
   - Not relevant to character animation pipeline
   - Animation quality is subjective (feedback loop handles it)

3. **Hermes/OpenClaw Skill Sources** — LLM skill repos
   - Animation skills custom-built, not generic

4. **Morning Digest Agent** — Personal briefing use case
   - Not relevant to animation generation

5. **Multi-Model Router** — Learns LLM-specific query patterns
   - Animation routing different (scene type, not query keywords)

---

### FUTURE (M5.2+)

1. **Learning System (TraceDrivenPolicy)**
   - Requires 2+ months of animation generation data
   - Learn optimal (scene_type → model, agent, skill_combination)
   - Cost/quality Pareto frontier

2. **GRPO Training Pipeline**
   - Generate SFT training data from best animation traces
   - Fine-tune animator agents on character-specific styles
   - Personalization loop

3. **Hybrid Agent Orchestration** (SkillOrchestra)
   - Complex multi-character animations as skill DAGs
   - Parallel rendering across character pairs
   - Dependency tracking and auto-retry

4. **Advanced Caching** — LLM KV cache techniques for animation
   - Cache character embeddings across scenes
   - Reuse skeleton/pose inference across similar frames

---

## 15. Implementation Roadmap

### Phase 1 (Foundation) — Q3 2026
**Effort:** 4 weeks, 1-2 engineers
- [ ] Clone & integrate OpenJarvis core (engine, agents, tools)
- [ ] Extend OllamaEngine for Wav2Lip/ComfyUI endpoints
- [ ] Build AnimationCoordinator agent (wrapping OrchestratorAgent)
- [ ] Implement AnimationTool interface for character-generator, scene-composer
- [ ] Connect to TaskScheduler for video generation jobs
- [ ] Basic telemetry (latency, GPU memory, frames generated)

**Deliverable:** E2E animation generation workflow via Jarvis-based coordinator

### Phase 2 (Observability) — Q4 2026
**Effort:** 3 weeks
- [ ] Integrate TraceStore for animation generation audit trail
- [ ] Build animation quality feedback loop (user ratings → traces)
- [ ] Connect TelemetryStore for cost/latency dashboards
- [ ] Extend Telegram channel for animation delivery

**Deliverable:** Observable, feedback-driven animation pipeline

### Phase 3 (Learning) — Q1 2027
**Effort:** 6 weeks
- [ ] Collect 100+ animation traces (different scenes, characters)
- [ ] Build TraceDrivenPolicy for scene-type → model routing
- [ ] Implement cost-aware routing (minimize $/frame)
- [ ] A/B test routing policies on real animations

**Deliverable:** Learned routing model for optimal animator selection

### Phase 4 (Scale) — Q2 2027
**Effort:** 4 weeks
- [ ] Implement SkillOrchestra for complex multi-character videos
- [ ] Add render farm load balancing
- [ ] Parallel skill execution (multi-scene rendering)
- [ ] Performance profiling & optimization

**Deliverable:** Production-ready animation pipeline (10x throughput)

---

## 16. Code Examples

### Example: AnimationCoordinator using OrchestratorAgent

```python
from openjarvis import Jarvis
from openjarvis.agents import OrchestratorAgent
from openjarvis.tools import BaseTool

class CharacterGeneratorTool(BaseTool):
    """Generate character mesh + rig for given description."""
    spec = ToolSpec(
        name="character_generator",
        description="Generate 3D character mesh and skeleton",
        arguments={
            "character_name": {"type": "string"},
            "style": {"type": "string", "enum": ["realistic", "cartoon", "anime"]},
            "age_group": {"type": "string"}
        }
    )
    
    def execute(self, character_name: str, style: str, age_group: str) -> ToolResult:
        # Call Runway or ComfyUI API
        # Returns: character_id, mesh_url, rig_params
        ...

class SceneComposerTool(BaseTool):
    """Compose multiple characters in a scene."""
    ...

class AnimationCoordinator:
    def __init__(self):
        jarvis = Jarvis()
        self.agent = OrchestratorAgent(
            engine=jarvis._engine,
            model="qwen3:14b",  # Multimodal reasoning
            tools=[
                CharacterGeneratorTool(),
                SceneComposerTool(),
                VoiceSyncTool(),
                RenderTool(),
            ],
            max_turns=10
        )
    
    def generate_animation(self, prompt: str) -> Dict:
        result = self.agent.run(prompt)
        # Agent autonomously:
        # 1. Breaks down prompt into characters/scenes
        # 2. Generates each character
        # 3. Composes scene layout
        # 4. Syncs voice timing
        # 5. Renders video
        return {
            "video_url": result.content,
            "metadata": result.tool_results
        }

# Usage
coordinator = AnimationCoordinator()
video = coordinator.generate_animation("Create a video of Alice and Bob discussing AI")
```

### Example: Animation Skill Definition

**File:** `~/.openjarvis/skills/character-animator/SKILL.md`

```yaml
---
name: character-animator
version: "1.0.0"
description: "Animate a character through a sequence of poses"
author: "SaathiOS Team"
depends:
  - pose-generator
  - ik-solver
tags: ["animation", "character"]
required_capabilities: ["gpu_inference"]
---

# Character Animator

Animates a 3D character through a smooth sequence of poses using inverse kinematics.

## Steps

1. Generate keyframe poses from motion description
2. Solve inverse kinematics constraints
3. Interpolate between keyframes
4. Render frames to video
```

### Example: Integration with Telegram

```python
from openjarvis.channels import TelegramChannel

async def handle_animation_request(message):
    """User sends /animate prompt via Telegram."""
    coordinator = AnimationCoordinator()
    
    # Long-running animation job
    video_url = await coordinator.generate_animation(message.text)
    
    # Publish result via Telegram
    await TelegramChannel.send(
        chat_id=message.chat_id,
        video_url=video_url,
        caption="Your animation is ready!"
    )
```

---

## 17. Conclusion

**OpenJarvis is a robust, extensible foundation for SaathiOS character animation pipeline:**

### Strengths
- ✓ Five well-designed primitives (easily extended for animation)
- ✓ Proven multi-turn agent orchestration (works for complex workflows)
- ✓ Flexible inference backend support (Ollama + cloud fallback)
- ✓ Strong observability (traces, telemetry, auditing)
- ✓ Local-first design (data privacy, cost control)
- ✓ Permissive licensing (no restrictions on commercial use)

### Necessary Adaptations
- ⚠ Animation-specific model catalog (custom metadata)
- ⚠ Custom agents for animation workflow (not generic LLM tasks)
- ⚠ Bespoke voice/audio integration (not generic channels)
- ⚠ Animator-aware cost tracking (per-frame, not per-token)

### Timeline & Effort
- **Phase 1 (Foundation):** 4 weeks, 1-2 engineers
- **Phase 2-4 (Production):** 12 weeks, 2-3 engineers
- **Total to M5.1 readiness:** 16 weeks (4 months)

### Recommendation
**Proceed with Phase 1 integration.** OpenJarvis provides 60-70% of required infrastructure; custom animation layers (15-20%) + operational tuning (10-15%) complete the system. No architectural conflicts detected.

---

## Appendix: Key Files & Paths

### Core Architecture Files
- `src/openjarvis/core/config.py` — JarvisConfig, hardware detection (1200 LOC)
- `src/openjarvis/core/registry.py` — RegistryBase[T], typed registries (250 LOC)
- `src/openjarvis/system.py` — JarvisSystem, SystemBuilder (500 LOC)
- `docs/architecture/overview.md` — Five-primitive design overview

### Engine Implementation
- `src/openjarvis/engine/_base.py` — InferenceEngine ABC
- `src/openjarvis/engine/ollama.py` — Ollama backend (350 LOC)
- `src/openjarvis/engine/cloud.py` — Cloud backends (900 LOC)
- `src/openjarvis/engine/_discovery.py` — Engine discovery, health checks

### Agent Framework
- `src/openjarvis/agents/_stubs.py` — BaseAgent, ToolUsingAgent ABCs
- `src/openjarvis/agents/orchestrator.py` — OrchestratorAgent (400 LOC)
- `src/openjarvis/agents/hybrid/` — Advanced orchestration (research)

### Skills & Tools
- `src/openjarvis/skills/manager.py` — SkillManager (500 LOC)
- `src/openjarvis/tools/_stubs.py` — BaseTool ABC, ToolSpec
- `src/openjarvis/tools/storage/` — Memory backends

### Security
- `src/openjarvis/security/guardrails.py` — GuardrailsEngine wrapper
- `src/openjarvis/security/audit.py` — AuditLogger

### Observability
- `src/openjarvis/traces/store.py` — TraceStore, trace persistence
- `src/openjarvis/telemetry/store.py` — TelemetryStore, metrics
- `src/openjarvis/traces/analyzer.py` — Aggregated statistics

### Learning
- `src/openjarvis/learning/router.py` — HeuristicRouter (200 LOC)
- `src/openjarvis/learning/trace_policy.py` — TraceDrivenPolicy (300 LOC)

---

**End of Analysis Document**
