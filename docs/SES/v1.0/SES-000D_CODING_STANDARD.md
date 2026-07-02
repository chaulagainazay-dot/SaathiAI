```
================================================================================
SaathiAI Engineering Specification (SES)
================================================================================
Document Title      : Coding Standard
Document ID         : SES-000D
Version             : 0.1.0
Status              : Draft
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

---

## Purpose

This document defines the coding conventions that govern every line of code written for SaathiAI. These are not style preferences — they are the shared language that makes the codebase readable by both human engineers and AI coding agents.

The goal is a codebase where:
- Any engineer can open any file and understand its purpose without prior context
- Any AI coding agent can read any module and add to it without breaking existing conventions
- Any reviewer can evaluate a pull request without needing to know who wrote it

This document covers Python conventions (the primary language), FastAPI conventions, LLM integration conventions, and security conventions. Frontend (React/JavaScript) conventions for pielts are out of scope and managed separately.

---

## Audience

| Role | Required Sections | Notes |
|------|------------------|-------|
| Software Engineers | All | Apply to every line written |
| AI Coding Agents | All | Every section is a constraint — match existing patterns exactly |
| Code Reviewers | All | Any deviation from this standard is a review finding |

---

## Reading Order

```
SES-000A Document Standard
        │
        ▼
SES-000C Architecture Principles
        │
        ▼
SES-000D Coding Standard  ← You are here
```

---

## Document Structure

| Section | Title | Summary |
|---------|-------|---------|
| Part 1 | Python Conventions | Naming, typing, structure |
| Part 2 | FastAPI Conventions | Endpoint design, Pydantic models, middleware |
| Part 3 | LLM Integration Conventions | Prompt templates, model calls, error handling |
| Part 4 | Database Conventions | SQLite schema, query patterns, migrations |
| Part 5 | Tool Module Conventions | How tool modules are structured and registered |
| Part 6 | Testing Conventions | Test structure, naming, coverage requirements |
| Part 7 | Security Conventions | Secrets, validation, logging rules |
| Part 8 | Commit and Branch Conventions | Git workflow for SaathiAI |

---

# Part 1 — Python Conventions

### 1.1 Language Version

Python 3.11 minimum. All new code targets Python 3.11+.

### 1.2 Type Annotations

All function parameters and return types must be annotated. No untyped `def`.

```python
# Correct
def get_context(user_id: str, limit: int = 20) -> list[dict]:
    ...

# Violation
def get_context(user_id, limit=20):
    ...
```

### 1.3 Naming Conventions

| Entity | Convention | Example |
|--------|-----------|---------|
| Modules | `snake_case` | `memory_manager.py` |
| Classes | `PascalCase` | `EpisodicMemory` |
| Functions | `snake_case` | `get_recent_context` |
| Constants | `SCREAMING_SNAKE_CASE` | `MAX_CONTEXT_LENGTH` |
| Private methods | `_leading_underscore` | `_validate_input` |
| Type aliases | `PascalCase` | `MemoryEntry = dict[str, Any]` |

### 1.4 Imports

Standard import order (enforced by `isort`):
1. Standard library
2. Third-party libraries
3. SaathiAI internal modules

No wildcard imports: `from module import *` is prohibited.

### 1.5 File Length

No Python file exceeds 400 lines. If a file approaches 400 lines, extract a cohesive unit to a new module. A file at 600 lines is a code review finding.

### 1.6 Comments

Comments explain WHY, not WHAT. Code explains what it does. Comments explain why the code does it that way.

```python
# Correct — explains non-obvious constraint
# deque maxlen=20 to bound Working Memory to the last 20 turns;
# Groq's context window handles the rest
self.working_memory = deque(maxlen=20)

# Violation — restates what the code says
# Create a deque with max length 20
self.working_memory = deque(maxlen=20)
```

No docstrings on private methods. One-line docstrings permitted on public methods when the function name alone is insufficient.

---

# Part 2 — FastAPI Conventions

### 2.1 Router Structure

Each subsystem has its own router file at `app/routers/<subsystem>.py`. The main `app/main.py` only imports and mounts routers.

```python
# app/main.py
from app.routers import memory, agents, voice, scheduler

app.include_router(memory.router, prefix="/api/v1/memory")
app.include_router(agents.router, prefix="/api/v1/agents")
```

### 2.2 Endpoint Naming

```
POST /api/v1/<subsystem>/<action>
GET  /api/v1/<subsystem>/<resource>/{id}
```

No verbs in resource paths beyond the HTTP method.

### 2.3 Request and Response Models

Every endpoint has a Pydantic request model and a Pydantic response model. No `dict` in or out.

```python
class MemoryContextRequest(BaseModel):
    user_id: str
    limit: int = 20

class MemoryContextResponse(BaseModel):
    status: Literal["success", "error"]
    data: list[MemoryEntry] | None = None
    error: str | None = None
    request_id: str
    duration_ms: int
```

### 2.4 Standard Response Envelope

Every endpoint returns the standard envelope defined in AP-08 (SES-000C). Use the `APIResponse` helper:

```python
from app.core.response import api_success, api_error

@router.post("/context")
async def get_context(req: MemoryContextRequest) -> MemoryContextResponse:
    try:
        data = await memory_service.get_context(req.user_id, req.limit)
        return api_success(data)
    except Exception as e:
        return api_error(str(e))
```

### 2.5 Error Handling

No bare `except Exception`. Catch specific exceptions. Log all errors with structured context.

```python
# Correct
except MemoryNotFoundError as e:
    logger.error("memory_not_found", user_id=req.user_id, error=str(e))
    return api_error("Memory not found", status_code=404)

# Violation
except Exception as e:
    return {"error": str(e)}
```

---

# Part 3 — LLM Integration Conventions

### 3.1 All LLM Calls Go Through the Provider Abstraction

See AP-02 (SES-000C). Never call a provider SDK directly from a tool module or agent.

```python
# Correct
from app.providers.llm_provider import llm

response = await llm.complete(
    prompt=prompt,
    model="standard",   # routes to groq llama-3.3-70b-versatile
    max_tokens=500
)

# Violation
import groq
client = groq.Groq(api_key=os.environ["GROQ_API_KEY"])
response = client.chat.completions.create(...)
```

### 3.2 Model Selection Labels

Use semantic model labels, not provider-specific model names, in business logic:

| Label | Routes To | Use When |
|-------|-----------|---------|
| `"screening"` | Shimmy (TinyLlama 1.1B) | High-volume classification, binary decisions |
| `"standard"` | Groq llama-3.3-70b-versatile | Most tasks |
| `"reasoning"` | Claude (Anthropic) | Complex multi-step reasoning |
| `"multimodal"` | Gemini | Image or audio input required |
| `"private"` | Ollama (local) | Sensitive data that must not leave the device |

### 3.3 Prompt Templates

All prompts are defined in `app/prompts/<module>.py`, not inline in tool modules or agents.

```python
# app/prompts/memory.py
CONTEXT_SUMMARY_PROMPT = """
You are summarizing a conversation history.
History: {history}
Summarize in 3 sentences maximum.
""".strip()

# Usage in tool module
from app.prompts.memory import CONTEXT_SUMMARY_PROMPT
prompt = CONTEXT_SUMMARY_PROMPT.format(history=history_text)
```

### 3.4 All LLM Calls Are Wrapped in Opik Traces

```python
from app.observability import opik_trace

async with opik_trace("memory_summary", model="standard") as trace:
    response = await llm.complete(prompt=prompt, model="standard")
    trace.log_tokens(response.usage)
```

---

# Part 4 — Database Conventions

### 4.1 Schema Initialization

All table definitions are in `app/db/schema.py` under `init_db()`. No table is created outside this function.

### 4.2 Column Naming

`snake_case`. Timestamps named `created_at`, `updated_at`. Foreign keys named `<table>_id`.

### 4.3 Query Pattern

No raw SQL strings in router or service files. All SQL in `app/db/<model>.py` files.

```python
# Correct — SQL in the model file
# app/db/memory.py
async def get_recent_entries(user_id: str, limit: int) -> list[MemoryEntry]:
    async with get_connection() as conn:
        rows = await conn.execute(
            "SELECT * FROM episodic_memory WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        )
        return [MemoryEntry(**row) for row in rows.fetchall()]
```

### 4.4 WAL Mode

All SQLite connections must enable WAL mode:

```python
conn.execute("PRAGMA journal_mode=WAL")
```

This is handled by the `get_connection()` context manager. Do not bypass it.

---

# Part 5 — Tool Module Conventions

### 5.1 Structure

Each tool module is a single Python file in `app/tools/<category>/<name>.py`.

Every tool module exports exactly one primary function, named the same as the module file.

```python
# app/tools/research/research_web.py

async def research_web(query: str, max_results: int = 5) -> ResearchResult:
    """Search the web and return structured results."""
    ...
```

### 5.2 Registration

Tools are registered in `app/tools/registry.py`:

```python
TOOL_REGISTRY = {
    "research_web": research_web,
    "send_telegram": send_telegram,
    "generate_content": generate_content,
    ...
}
```

### 5.3 Tool Function Signature Rules

- All parameters typed
- All parameters with defaults have explicit defaults
- Return type is always a Pydantic model, never `dict`
- Tool functions are `async`

---

# Part 6 — Testing Conventions

### 6.1 Test File Location

Test files mirror the source structure under `tests/`:

```
app/tools/research/research_web.py
tests/tools/research/test_research_web.py
```

### 6.2 Test Naming

```python
def test_research_web_returns_results_for_valid_query():
    ...

def test_research_web_raises_on_empty_query():
    ...
```

Pattern: `test_<function>_<outcome>_<condition>`.

### 6.3 Test Independence

No test depends on the state set by another test. Each test sets up its own fixtures and tears down after itself.

### 6.4 No Real LLM Calls in Unit Tests

Unit tests use mock providers, not real LLM calls. Integration tests may use real providers but are explicitly marked:

```python
@pytest.mark.integration
def test_llm_provider_completes_standard_prompt():
    ...
```

### 6.5 Coverage Requirement

All new code must have 80% test coverage measured by `pytest-cov`. Coverage below 80% is a code review finding.

---

# Part 7 — Security Conventions

See also AP-07 (SES-000C) for the architectural principle. This section covers implementation specifics.

### 7.1 Environment Variables

All secrets in `.env`. Access via `os.environ.get()` with a descriptive name. Never `os.environ["KEY"]` — use `.get()` with a fallback that fails loudly at startup, not silently at runtime.

```python
# Correct
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise EnvironmentError("GROQ_API_KEY is required")

# Violation
GROQ_API_KEY = os.environ["GROQ_API_KEY"]  # Raises unclear KeyError at runtime
```

### 7.2 Input Validation

All user-supplied input validated with Pydantic at the endpoint. No raw string operations on user input in business logic.

### 7.3 Logging Rules

Never log: API keys, passwords, tokens, user PII, or full request bodies containing any of the above.

Always log: request IDs, operation names, duration, success/failure, and anonymized error context.

---

# Part 8 — Commit and Branch Conventions

### 8.1 Commit Message Format

```
<type>(<scope>): <description>

[optional body]
[optional footer]
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`

Examples:
```
feat(memory): add ChromaDB vector search to semantic tier
fix(scheduler): prevent duplicate job registration on restart
docs(ses): add SES-000D coding standard
```

### 8.2 Branch Naming

```
<type>/<description-in-kebab-case>

feat/voice-os-pipecat-integration
fix/scheduler-duplicate-jobs
docs/ses-000d-coding-standard
```

### 8.3 Commit Frequency

Commit at every logical checkpoint — after writing tests, after making tests pass, after a refactor. Do not accumulate uncommitted changes across multiple features.

---

# Acceptance Criteria

| # | Criterion | Verification Method | Priority |
|---|-----------|---------------------|----------|
| AC-001 | No Python file in `app/` exceeds 400 lines | `find app/ -name "*.py" -exec wc -l {} \; \| awk '$1 > 400'` | Must Have |
| AC-002 | No direct LLM provider SDK imports outside `app/providers/` | `grep -r "import groq\|import anthropic\|import google.generativeai" app/ --include="*.py" \| grep -v providers/` | Must Have |
| AC-003 | All functions have type annotations | `mypy app/ --ignore-missing-imports` passes with zero errors | Should Have |
| AC-004 | Test coverage ≥ 80% for all new code | `pytest --cov=app --cov-fail-under=80` | Should Have |
| AC-005 | No secrets in source code | `git log --all --grep="api_key\|password\|secret" --all -p` returns zero matches | Must Have |

---

# Implementation Checklist

**Phase 1 — Standard Definition**
- [x] Define Python conventions
- [x] Define FastAPI conventions
- [x] Define LLM integration conventions
- [x] Define database conventions
- [x] Define tool module conventions
- [x] Define testing conventions
- [x] Define security conventions
- [x] Define commit conventions

**Phase 2 — Enforcement**
- [ ] Configure `isort` and `black` in `pyproject.toml`
- [ ] Configure `mypy` in `pyproject.toml`
- [ ] Add pre-commit hooks for linting and secret scanning
- [ ] Add coverage gate to CI pipeline

---

# Risks

| # | Risk | Probability | Impact | Mitigation |
|---|------|-------------|--------|------------|
| R-001 | Existing code does not comply with these standards | High | Low | Document existing violations; apply standards to all new code immediately; refactor existing code incrementally |

---

# Dependencies

**Internal:** SES-000C Architecture Principles (AP-02, AP-07 referenced here)

**External:** Python 3.11+, FastAPI, Pydantic v2, pytest, mypy, black, isort, pytest-cov

---

# Related Documents

| Document ID | Title | Relationship |
|-------------|-------|-------------|
| SES-000C | Architecture Principles | AP-02 and AP-07 are enforced through coding conventions |
| SES-001 | Architecture | Implements the module structure described here |

---

*End of SES-000D Coding Standard — Version 0.1.0*

*Status: Draft (L1)*

*Next: [`SES-000E_REPOSITORY_INDEX.md`](SES-000E_REPOSITORY_INDEX.md)*
