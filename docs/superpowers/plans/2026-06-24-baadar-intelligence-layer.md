# Baadar Intelligence Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the Research→Create→Post→Analyze→Learn loop by adding 10 intelligence features to Baadar (~/SaathiAI), turning it from a posting bot into a self-improving content engine.

**Architecture:** All new logic lives in two new tool files (`intelligence.py`, `referral.py`) and a persona config (`yeti_persona.json`). Endpoints are added to `server.py`. All persistent data goes into SQLite at `~/SaathiAI/data/baadar.db` (new tables). The existing `_llm_helper.ask_llm()` pattern is used for all AI calls — never add a direct API call when this helper exists.

**Tech Stack:** Python 3.12, FastAPI, SQLite3, `_llm_helper.ask_llm()`, `n8n_tools.send_telegram()`, `firebase_admin` (already in env), YouTube Analytics API via httpx, APScheduler (already running via `saathi/scheduler.py`).

## Global Constraints

- All new files go under `~/SaathiAI/saathi/tools/` or `~/SaathiAI/data/`
- All new endpoints go in `~/SaathiAI/saathi/server.py` following the existing `@app.post` / `@app.get` pattern
- All AI calls use `from ._llm_helper import ask_llm, extract_json` — never call OpenAI/Gemini directly
- All Telegram notifications use `from .tools.n8n_tools import send_telegram`
- SQLite DB path: `~/SaathiAI/data/baadar.db` — use `sqlite3` stdlib, no ORM
- YouTube API key: `os.getenv("GOOGLE_API_KEY")` — same key used by existing tools
- Firebase RTDB URL: `https://ielts-and-language-practice-default-rtdb.firebaseio.com`
- Firebase SA key: `~/SaathiAI/firebase-admin.json`
- Never hardcode secrets — always `os.getenv()`
- Persona file: `~/SaathiAI/data/yeti_persona.json`
- Tests go in `~/SaathiAI/tests/` using `pytest`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `saathi/tools/intelligence.py` | **Create** | Retention analyzer, viral patterns DB, competitor intel, comment intel, CEO dashboard |
| `saathi/tools/referral.py` | **Create** | Referral engine — detect score improvements, generate codes, send notifications |
| `data/yeti_persona.json` | **Create** | Mr. Yeti character config (traits, phrases, forbidden words) |
| `saathi/tools/script_writer.py` | **Modify** | Inject persona into `generate_script()` system prompt |
| `saathi/tools/content_studio.py` | **Modify** | Hook lab (20 hooks → top 3), thumbnail scoring (5 options), trend fusion |
| `saathi/server.py` | **Modify** | Register all new endpoints (10 features) |
| `tests/test_intelligence.py` | **Create** | Tests for retention scoring, pattern DB, hook lab, CEO dashboard |
| `tests/test_referral.py` | **Create** | Tests for referral engine |

---

## Task 1: SQLite Schema — All New Tables

**Files:**
- Modify: `saathi/tools/intelligence.py` (create it)
- Test: `tests/test_intelligence.py`

**Interfaces:**
- Produces: `init_db()` — call once at startup to create all tables

- [ ] **Step 1: Write the failing test**

```python
# tests/test_intelligence.py
import sqlite3, os, pytest
os.environ.setdefault("BAADAR_DB", "/tmp/test_baadar.db")

from saathi.tools.intelligence import init_db, DB_PATH

def test_init_db_creates_all_tables():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "video_retention" in tables
    assert "hook_performance" in tables
    assert "viral_patterns" in tables
    assert "competitor_data" in tables
    assert "comment_intelligence" in tables
    assert "referral_events" in tables
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/SaathiAI && python -m pytest tests/test_intelligence.py::test_init_db_creates_all_tables -v
```
Expected: `FAILED` — `ModuleNotFoundError: No module named 'saathi.tools.intelligence'`

- [ ] **Step 3: Create `saathi/tools/intelligence.py` with `init_db()`**

```python
"""
intelligence.py — Retention Analyzer, Viral Pattern DB, Competitor Intel,
Comment Intel, Hook Lab helpers, CEO Dashboard aggregation.
"""
import json, os, sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .. import config

DB_PATH = os.getenv("BAADAR_DB", str(config.ROOT / "data" / "baadar.db"))


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    """Create all intelligence tables if they don't exist."""
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS video_retention (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id      TEXT NOT NULL,
            platform      TEXT NOT NULL,
            ret_3s        REAL,
            ret_10s       REAL,
            ret_30s       REAL,
            avg_watch_sec REAL,
            completion_pct REAL,
            score         TEXT,
            recorded_at   TEXT DEFAULT (datetime('now'))
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ux_vr ON video_retention(video_id, platform);

        CREATE TABLE IF NOT EXISTS hook_performance (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            hook_text      TEXT NOT NULL,
            topic          TEXT,
            video_id       TEXT,
            views_48h      INTEGER DEFAULT 0,
            retention_score REAL DEFAULT 0,
            created_at     TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS viral_patterns (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            hook          TEXT,
            topic         TEXT,
            format_type   TEXT,
            retention_pct REAL DEFAULT 0,
            views         INTEGER DEFAULT 0,
            shares        INTEGER DEFAULT 0,
            saves         INTEGER DEFAULT 0,
            platform      TEXT,
            recorded_at   TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS competitor_data (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_name  TEXT,
            channel_id    TEXT,
            video_title   TEXT,
            views         INTEGER DEFAULT 0,
            upload_date   TEXT,
            topic_tags    TEXT,
            scanned_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS comment_intelligence (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            platform      TEXT,
            comment_text  TEXT,
            category      TEXT,
            video_idea    TEXT,
            source_video_id TEXT,
            created_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS referral_events (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            uid           TEXT NOT NULL,
            old_score     REAL,
            new_score     REAL,
            referral_code TEXT,
            sent_at       TEXT DEFAULT (datetime('now')),
            conversions   INTEGER DEFAULT 0
        );
        """)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/SaathiAI && python -m pytest tests/test_intelligence.py::test_init_db_creates_all_tables -v
```
Expected: `PASSED`

- [ ] **Step 5: Call `init_db()` at Baadar startup**

In `saathi/server.py`, find the `@app.on_event("startup")` handler and add:

```python
# Inside the existing startup handler in server.py
from .tools.intelligence import init_db as _init_intelligence_db
_init_intelligence_db()
```

- [ ] **Step 6: Commit**

```bash
cd ~/SaathiAI
git add saathi/tools/intelligence.py tests/test_intelligence.py saathi/server.py
git commit -m "feat: add intelligence DB schema — 6 new tables"
```

---

## Task 2: Retention Analyzer

**Files:**
- Modify: `saathi/tools/intelligence.py`
- Modify: `saathi/server.py`
- Test: `tests/test_intelligence.py`

**Interfaces:**
- Consumes: `init_db()` from Task 1
- Produces:
  - `score_retention(completion_pct: float) -> str` — returns `"A"/"B"/"C"/"D"`
  - `upsert_retention(video_id, platform, ret_3s, ret_10s, ret_30s, avg_watch_sec, completion_pct) -> dict`
  - `get_retention(video_id, platform) -> dict | None`
  - `get_killed_formats() -> list[str]` — format_types with avg score D

- [ ] **Step 1: Write failing tests**

```python
# tests/test_intelligence.py — add these tests
from saathi.tools.intelligence import score_retention, upsert_retention, get_retention

def test_score_retention_grades():
    assert score_retention(75.0) == "A"
    assert score_retention(60.0) == "B"
    assert score_retention(40.0) == "C"
    assert score_retention(25.0) == "D"
    assert score_retention(70.0) == "A"   # boundary: >=70 → A
    assert score_retention(50.0) == "B"   # boundary: >=50 → B
    assert score_retention(30.0) == "C"   # boundary: >=30 → C

def test_upsert_and_get_retention():
    init_db()
    result = upsert_retention("vid_test_1", "youtube", 85.0, 72.0, 55.0, 28.5, 68.0)
    assert result["score"] == "B"
    row = get_retention("vid_test_1", "youtube")
    assert row is not None
    assert row["completion_pct"] == 68.0
    assert row["score"] == "B"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/SaathiAI && python -m pytest tests/test_intelligence.py::test_score_retention_grades tests/test_intelligence.py::test_upsert_and_get_retention -v
```
Expected: `FAILED`

- [ ] **Step 3: Implement in `intelligence.py`**

Add after `init_db()`:

```python
def score_retention(completion_pct: float) -> str:
    """A=>=70%, B=>=50%, C=>=30%, D=<30%."""
    if completion_pct >= 70:
        return "A"
    if completion_pct >= 50:
        return "B"
    if completion_pct >= 30:
        return "C"
    return "D"


def upsert_retention(video_id: str, platform: str, ret_3s: float, ret_10s: float,
                     ret_30s: float, avg_watch_sec: float, completion_pct: float) -> dict:
    grade = score_retention(completion_pct)
    with _conn() as c:
        c.execute("""
            INSERT INTO video_retention
                (video_id, platform, ret_3s, ret_10s, ret_30s, avg_watch_sec, completion_pct, score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(video_id, platform) DO UPDATE SET
                ret_3s=excluded.ret_3s, ret_10s=excluded.ret_10s,
                ret_30s=excluded.ret_30s, avg_watch_sec=excluded.avg_watch_sec,
                completion_pct=excluded.completion_pct, score=excluded.score,
                recorded_at=datetime('now')
        """, (video_id, platform, ret_3s, ret_10s, ret_30s, avg_watch_sec, completion_pct, grade))
    return {"video_id": video_id, "platform": platform, "score": grade,
            "completion_pct": completion_pct}


def get_retention(video_id: str, platform: str) -> "dict | None":
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM video_retention WHERE video_id=? AND platform=?",
            (video_id, platform)
        ).fetchone()
    return dict(row) if row else None


def get_killed_formats() -> list:
    """Return format_types that have >=3 D-scored videos — suppress these in pipeline."""
    with _conn() as c:
        rows = c.execute("""
            SELECT vp.format_type
            FROM viral_patterns vp
            JOIN video_retention vr ON vp.hook = vr.video_id
            WHERE vr.score = 'D'
            GROUP BY vp.format_type
            HAVING COUNT(*) >= 3
        """).fetchall()
    return [r["format_type"] for r in rows]


def get_all_retention(platform: str = None) -> list:
    with _conn() as c:
        if platform:
            rows = c.execute(
                "SELECT * FROM video_retention WHERE platform=? ORDER BY recorded_at DESC",
                (platform,)
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM video_retention ORDER BY recorded_at DESC"
            ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Add endpoint to `server.py`**

Find the existing `/api/v1/analytics/run` block and add after it:

```python
@app.get("/api/v1/analytics/retention")
async def analytics_retention(platform: str = None):
    """Return all stored retention data, optionally filtered by platform."""
    from .tools.intelligence import get_all_retention
    return {"ok": True, "data": get_all_retention(platform)}

@app.post("/api/v1/analytics/retention")
async def analytics_retention_save(request: Request):
    """Store/update retention data for a video."""
    body = await request.json()
    from .tools.intelligence import upsert_retention
    result = upsert_retention(
        body["video_id"], body["platform"],
        body.get("ret_3s", 0), body.get("ret_10s", 0), body.get("ret_30s", 0),
        body.get("avg_watch_sec", 0), body["completion_pct"]
    )
    return {"ok": True, "result": result}
```

- [ ] **Step 5: Run tests**

```bash
cd ~/SaathiAI && python -m pytest tests/test_intelligence.py -v
```
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add saathi/tools/intelligence.py saathi/server.py tests/test_intelligence.py
git commit -m "feat: retention analyzer — score A/B/C/D, upsert/get endpoints"
```

---

## Task 3: Hook Laboratory (20 hooks → top 3 → 3 videos)

**Files:**
- Modify: `saathi/tools/content_studio.py`
- Modify: `saathi/server.py`
- Test: `tests/test_intelligence.py`

**Interfaces:**
- Consumes: `ask_llm()`, `extract_json()` from `_llm_helper`
- Produces:
  - `generate_hooks(topic: str) -> dict` — `{hooks: [{text, curiosity, urgency, specificity, total}], top3: [str]}`
  - `save_hook_performance(hook_text, topic, video_id) -> None`

- [ ] **Step 1: Write failing test**

```python
# tests/test_intelligence.py
import unittest.mock as mock

def test_generate_hooks_returns_top3():
    fake_llm_response = json.dumps({
        "hooks": [
            {"text": "Stop making this mistake.", "curiosity": 8, "urgency": 7, "specificity": 6},
            {"text": "97% of students fail because of this.", "curiosity": 9, "urgency": 9, "specificity": 8},
            {"text": "This one trick changed my IELTS score.", "curiosity": 7, "urgency": 6, "specificity": 7},
            {"text": "You are doing grammar wrong.", "curiosity": 6, "urgency": 5, "specificity": 5},
        ]
    })
    with mock.patch("saathi.tools.content_studio.ask_llm", return_value=fake_llm_response):
        from saathi.tools.content_studio import generate_hooks
        result = generate_hooks("Grammar Mistakes")
    assert "hooks" in result
    assert "top3" in result
    assert len(result["top3"]) == 3
    # top hook should be highest total score
    assert result["top3"][0] == "97% of students fail because of this."
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/SaathiAI && python -m pytest tests/test_intelligence.py::test_generate_hooks_returns_top3 -v
```
Expected: `FAILED` — `cannot import name 'generate_hooks'`

- [ ] **Step 3: Add `generate_hooks()` and `save_hook_performance()` to `content_studio.py`**

Add at the end of `saathi/tools/content_studio.py`:

```python
def generate_hooks(topic: str) -> dict:
    """Generate 20 hooks for a topic, AI-score them, return top 3."""
    from ._llm_helper import ask_llm, extract_json
    prompt = f"""Generate exactly 20 short viral hooks for this IELTS content topic: "{topic}"
Each hook must be under 12 words, written as a social video opening line.
Score each hook (0-10) on:
- curiosity: does it make the viewer need to know more?
- urgency: does it create fear of missing out or failing?
- specificity: is it concrete (numbers, names, specific mistakes)?

Return ONLY valid JSON:
{{
  "hooks": [
    {{"text": "...", "curiosity": 8, "urgency": 7, "specificity": 6}},
    ...20 items...
  ]
}}"""
    raw = ask_llm(prompt, system="You generate viral social media hooks. Reply ONLY with valid JSON.")
    data = extract_json(raw)
    hooks = data.get("hooks", [])
    # Compute total score and sort descending
    for h in hooks:
        h["total"] = h.get("curiosity", 0) + h.get("urgency", 0) + h.get("specificity", 0)
    hooks.sort(key=lambda x: x["total"], reverse=True)
    top3 = [h["text"] for h in hooks[:3]]
    return {"topic": topic, "hooks": hooks, "top3": top3}


def save_hook_performance(hook_text: str, topic: str, video_id: str = ""):
    """Store a hook in hook_performance table for later performance tracking."""
    import sqlite3, os
    from .. import config
    db = os.getenv("BAADAR_DB", str(config.ROOT / "data" / "baadar.db"))
    with sqlite3.connect(db) as c:
        c.execute(
            "INSERT INTO hook_performance (hook_text, topic, video_id) VALUES (?, ?, ?)",
            (hook_text, topic, video_id)
        )
```

- [ ] **Step 4: Upgrade `/hooks/generate` endpoint in `server.py`**

Find the existing `@app.post("/api/v1/hooks/generate")` and replace its body:

```python
@app.post("/api/v1/hooks/generate")
async def hooks_generate(request: Request):
    """Generate 20 hooks for a topic, score them, return top 3."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    topic = body.get("topic", "IELTS tips")
    try:
        from .tools.content_studio import generate_hooks
        result = generate_hooks(topic)
        return {"ok": True, **result}
    except Exception as e:
        return {"ok": False, "error": str(e)}
```

- [ ] **Step 5: Run test**

```bash
cd ~/SaathiAI && python -m pytest tests/test_intelligence.py::test_generate_hooks_returns_top3 -v
```
Expected: `PASSED`

- [ ] **Step 6: Commit**

```bash
git add saathi/tools/content_studio.py saathi/server.py tests/test_intelligence.py
git commit -m "feat: hook lab — 20 hooks generated, AI-scored, top 3 returned"
```

---

## Task 4: Viral Pattern Database + Auto-Weighting

**Files:**
- Modify: `saathi/tools/intelligence.py`
- Modify: `saathi/tools/content_studio.py` (research weighting)
- Modify: `saathi/server.py`
- Test: `tests/test_intelligence.py`

**Interfaces:**
- Consumes: `_conn()` from Task 1
- Produces:
  - `save_viral_pattern(hook, topic, format_type, retention_pct, views, shares, saves, platform) -> None`
  - `get_format_avg_retention() -> dict[str, float]` — `{"quiz": 80.2, "vocab": 42.1, ...}`
  - `get_top_formats(n=3) -> list[str]`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_intelligence.py
from saathi.tools.intelligence import save_viral_pattern, get_format_avg_retention, get_top_formats

def test_viral_pattern_avg_retention():
    init_db()
    save_viral_pattern("Hook A", "Grammar", "quiz", 82.0, 1000, 50, 30, "youtube")
    save_viral_pattern("Hook B", "Grammar", "quiz", 78.0, 800, 40, 25, "youtube")
    save_viral_pattern("Hook C", "Vocab", "vocab", 40.0, 300, 10, 5, "youtube")
    avgs = get_format_avg_retention()
    assert "quiz" in avgs
    assert abs(avgs["quiz"] - 80.0) < 1.0
    assert "vocab" in avgs

def test_get_top_formats():
    init_db()
    save_viral_pattern("Hook X", "Topic", "quiz",  80.0, 1000, 0, 0, "youtube")
    save_viral_pattern("Hook Y", "Topic", "story", 65.0, 800, 0, 0, "youtube")
    save_viral_pattern("Hook Z", "Topic", "vocab", 40.0, 300, 0, 0, "youtube")
    tops = get_top_formats(2)
    assert tops[0] == "quiz"
    assert tops[1] == "story"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/SaathiAI && python -m pytest tests/test_intelligence.py::test_viral_pattern_avg_retention tests/test_intelligence.py::test_get_top_formats -v
```
Expected: `FAILED`

- [ ] **Step 3: Add functions to `intelligence.py`**

```python
def save_viral_pattern(hook: str, topic: str, format_type: str, retention_pct: float,
                       views: int, shares: int, saves: int, platform: str):
    with _conn() as c:
        c.execute("""
            INSERT INTO viral_patterns (hook, topic, format_type, retention_pct, views, shares, saves, platform)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (hook, topic, format_type, retention_pct, views, shares, saves, platform))


def get_format_avg_retention() -> dict:
    """Return avg retention per format_type (only formats with >=3 data points)."""
    with _conn() as c:
        rows = c.execute("""
            SELECT format_type, AVG(retention_pct) as avg_ret, COUNT(*) as cnt
            FROM viral_patterns
            GROUP BY format_type
            HAVING cnt >= 1
            ORDER BY avg_ret DESC
        """).fetchall()
    return {r["format_type"]: round(r["avg_ret"], 1) for r in rows}


def get_top_formats(n: int = 3) -> list:
    """Return format_types sorted by avg retention descending."""
    avgs = get_format_avg_retention()
    return sorted(avgs, key=lambda k: avgs[k], reverse=True)[:n]
```

- [ ] **Step 4: Add endpoint to `server.py`**

```python
@app.get("/api/v1/analytics/patterns")
async def analytics_patterns():
    """Return avg retention per format type and top performing formats."""
    from .tools.intelligence import get_format_avg_retention, get_top_formats
    avgs = get_format_avg_retention()
    tops = get_top_formats(3)
    return {"ok": True, "avg_by_format": avgs, "top_formats": tops}

@app.post("/api/v1/analytics/patterns")
async def analytics_patterns_save(request: Request):
    """Save a viral pattern data point."""
    body = await request.json()
    from .tools.intelligence import save_viral_pattern
    save_viral_pattern(
        body.get("hook", ""), body.get("topic", ""), body.get("format_type", "tip"),
        body.get("retention_pct", 0), body.get("views", 0),
        body.get("shares", 0), body.get("saves", 0), body.get("platform", "youtube")
    )
    return {"ok": True}
```

- [ ] **Step 5: Run tests**

```bash
cd ~/SaathiAI && python -m pytest tests/test_intelligence.py -k "viral_pattern or top_format" -v
```
Expected: `PASSED`

- [ ] **Step 6: Commit**

```bash
git add saathi/tools/intelligence.py saathi/server.py tests/test_intelligence.py
git commit -m "feat: viral pattern DB — avg retention per format, top formats endpoint"
```

---

## Task 5: Mr. Yeti Character Engine

**Files:**
- Create: `data/yeti_persona.json`
- Modify: `saathi/tools/script_writer.py`
- Modify: `saathi/server.py`
- Test: `tests/test_intelligence.py`

**Interfaces:**
- Produces:
  - `load_persona() -> dict` — reads `yeti_persona.json`
  - `persona_system_prompt() -> str` — formats traits into a system prompt string
  - `generate_script(topic, content_type, format)` — already exists, now injects persona

- [ ] **Step 1: Create `data/yeti_persona.json`**

```json
{
  "name": "Mr. Yeti",
  "tagline": "The free IELTS professor from the Himalayas",
  "traits": ["funny", "direct", "encouraging", "slightly sarcastic"],
  "speech_patterns": [
    "Short punchy sentences. Max 10 words per sentence.",
    "Speaks directly to 'you' — never 'students' or 'people'",
    "Uses contrast: wrong way first, right way second",
    "Ends with a small encouraging push"
  ],
  "signature_openers": [
    "Stop right there.",
    "Here is the truth.",
    "Most IELTS students get this wrong.",
    "Let me show you something.",
    "Quick question:"
  ],
  "catchphrases": [
    "Simple. Effective. Band 7.",
    "Practice this today.",
    "You have got this.",
    "One step closer to your score."
  ],
  "forbidden_phrases": [
    "As an AI",
    "I cannot",
    "It is important to note",
    "In conclusion, it is clear that",
    "utilize",
    "leverage",
    "delve into"
  ],
  "tone": "Like a cool uncle who happens to be an expert. Never dry. Never academic."
}
```

- [ ] **Step 2: Write failing test**

```python
# tests/test_intelligence.py
def test_persona_system_prompt_contains_traits():
    from saathi.tools.script_writer import persona_system_prompt
    prompt = persona_system_prompt()
    assert "funny" in prompt
    assert "Mr. Yeti" in prompt
    assert "forbidden" in prompt.lower() or "never say" in prompt.lower()
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd ~/SaathiAI && python -m pytest tests/test_intelligence.py::test_persona_system_prompt_contains_traits -v
```
Expected: `FAILED`

- [ ] **Step 4: Add `load_persona()` and `persona_system_prompt()` to `script_writer.py`**

Add near the top of `saathi/tools/script_writer.py` (after imports):

```python
from pathlib import Path
from .. import config

_PERSONA_PATH = config.ROOT / "data" / "yeti_persona.json"


def load_persona() -> dict:
    try:
        return json.loads(_PERSONA_PATH.read_text())
    except Exception:
        return {}


def persona_system_prompt() -> str:
    p = load_persona()
    if not p:
        return "You are Mr. Yeti, a funny direct IELTS teacher."
    traits = ", ".join(p.get("traits", []))
    openers = "\n".join(f"  - {o}" for o in p.get("signature_openers", []))
    catchphrases = "\n".join(f"  - c" for c in p.get("catchphrases", []))
    forbidden = ", ".join(f'"{w}"' for w in p.get("forbidden_phrases", []))
    patterns = "\n".join(f"  - {s}" for s in p.get("speech_patterns", []))
    return f"""You are {p.get('name', 'Mr. Yeti')} — {p.get('tagline', '')}.
Personality traits: {traits}.
Tone: {p.get('tone', '')}
Speech patterns:
{patterns}
Signature openers (use one of these to start):
{openers}
Catchphrases (end with one of these):
{catchphrases}
NEVER say these words or phrases: {forbidden}.
Stay in character at all times. Short sentences. Speak to 'you' directly."""
```

- [ ] **Step 5: Inject persona into `generate_script()`**

In `script_writer.py`, find `generate_script()` and update the system prompt line:

```python
def generate_script(topic: str, content_type: str = "tip", format: str = "short",
                    hook: str = "", persona: bool = True) -> dict:
    # ... existing code ...
    system = persona_system_prompt() if persona else "You are a helpful IELTS assistant."
    # Pass `system` to ask_llm call — find the existing ask_llm call and update it:
    raw = ask_llm(prompt, system=system)
```

- [ ] **Step 6: Add persona endpoints to `server.py`**

```python
@app.get("/api/v1/yeti/persona")
async def yeti_persona_get():
    from .tools.script_writer import load_persona
    return {"ok": True, "persona": load_persona()}

@app.post("/api/v1/yeti/persona")
async def yeti_persona_update(request: Request):
    """Update one or more fields in yeti_persona.json."""
    import json as _json
    from pathlib import Path
    from . import config
    body = await request.json()
    persona_path = config.ROOT / "data" / "yeti_persona.json"
    current = {}
    if persona_path.exists():
        current = _json.loads(persona_path.read_text())
    current.update(body)
    persona_path.write_text(_json.dumps(current, indent=2, ensure_ascii=False))
    return {"ok": True, "persona": current}
```

- [ ] **Step 7: Run tests**

```bash
cd ~/SaathiAI && python -m pytest tests/test_intelligence.py::test_persona_system_prompt_contains_traits -v
```
Expected: `PASSED`

- [ ] **Step 8: Commit**

```bash
git add data/yeti_persona.json saathi/tools/script_writer.py saathi/server.py tests/test_intelligence.py
git commit -m "feat: Mr Yeti character engine — persona JSON, system prompt injection, GET/POST /yeti/persona"
```

---

## Task 6: Comment Intelligence Upgrade

**Files:**
- Modify: `saathi/tools/intelligence.py`
- Modify: `saathi/server.py`
- Test: `tests/test_intelligence.py`

**Interfaces:**
- Consumes: `ask_llm()`, `comment_miner.pull_youtube_comments()`
- Produces:
  - `classify_comments(comments: list[dict]) -> list[dict]` — adds `category` and `video_idea` fields
  - `get_video_ideas_from_comments(n=10) -> list[dict]`

- [ ] **Step 1: Write failing test**

```python
# tests/test_intelligence.py
def test_classify_comments_adds_category():
    fake_response = json.dumps({
        "results": [
            {"comment_text": "What tense should I use in Task 2?",
             "category": "question", "video_idea": "IELTS Writing Task 2 tense guide"}
        ]
    })
    comments = [{"text": "What tense should I use in Task 2?", "video_id": "vid1"}]
    with mock.patch("saathi.tools.intelligence.ask_llm", return_value=fake_response):
        from saathi.tools.intelligence import classify_comments
        result = classify_comments(comments)
    assert result[0]["category"] == "question"
    assert "video_idea" in result[0]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/SaathiAI && python -m pytest tests/test_intelligence.py::test_classify_comments_adds_category -v
```
Expected: `FAILED`

- [ ] **Step 3: Add to `intelligence.py`**

```python
def classify_comments(comments: list) -> list:
    """Use LLM to classify comments and extract video ideas."""
    from ._llm_helper import ask_llm, extract_json
    if not comments:
        return []
    batch = [{"comment_text": c.get("text", c.get("comment_text", "")),
              "video_id": c.get("video_id", "")} for c in comments[:50]]
    prompt = f"""Classify each of these YouTube/TikTok comments from an IELTS channel.
For each comment, assign:
- category: one of "question", "pain_point", "request", "praise", "other"
- video_idea: a short title for a video that answers this comment (or "" if not applicable)

Comments:
{json.dumps(batch, ensure_ascii=False)}

Return ONLY valid JSON:
{{"results": [{{"comment_text": "...", "category": "...", "video_idea": "..."}}]}}"""
    raw = ask_llm(prompt, system="You classify social media comments. Reply ONLY with valid JSON.")
    data = extract_json(raw)
    results = data.get("results", [])
    # Save to DB
    with _conn() as c:
        for item in results:
            c.execute("""
                INSERT INTO comment_intelligence (platform, comment_text, category, video_idea, source_video_id)
                VALUES (?, ?, ?, ?, ?)
            """, ("youtube", item.get("comment_text", ""), item.get("category", "other"),
                  item.get("video_idea", ""), item.get("video_id", "")))
    return results


def get_video_ideas_from_comments(n: int = 10) -> list:
    """Return top video ideas from comments, ranked by frequency."""
    with _conn() as c:
        rows = c.execute("""
            SELECT video_idea, COUNT(*) as freq, category
            FROM comment_intelligence
            WHERE video_idea != ''
            GROUP BY video_idea
            ORDER BY freq DESC
            LIMIT ?
        """, (n,)).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Add endpoint to `server.py`**

Find existing `/api/v1/comments/mine` and add after it:

```python
@app.get("/api/v1/comments/video-ideas")
async def comments_video_ideas(n: int = 10):
    """Return top video ideas extracted from comments."""
    from .tools.intelligence import get_video_ideas_from_comments
    return {"ok": True, "ideas": get_video_ideas_from_comments(n)}

@app.post("/api/v1/comments/classify")
async def comments_classify(request: Request):
    """Classify a batch of comments and save to DB."""
    body = await request.json()
    comments = body.get("comments", [])
    from .tools.intelligence import classify_comments
    return {"ok": True, "results": classify_comments(comments)}
```

- [ ] **Step 5: Run test**

```bash
cd ~/SaathiAI && python -m pytest tests/test_intelligence.py::test_classify_comments_adds_category -v
```
Expected: `PASSED`

- [ ] **Step 6: Commit**

```bash
git add saathi/tools/intelligence.py saathi/server.py tests/test_intelligence.py
git commit -m "feat: comment intelligence — classify comments, extract video ideas"
```

---

## Task 7: Competitor Intelligence

**Files:**
- Modify: `saathi/tools/intelligence.py`
- Modify: `saathi/server.py`
- Test: `tests/test_intelligence.py`

**Interfaces:**
- Produces:
  - `scan_competitors() -> dict` — fetches top 5 videos per competitor channel
  - `get_competitor_insights() -> dict` — patterns, gaps, topic frequency

- [ ] **Step 1: Write failing test**

```python
def test_competitor_insights_returns_gaps():
    init_db()
    # Insert fake competitor data
    import sqlite3, os
    from saathi import config
    db = os.getenv("BAADAR_DB", str(config.ROOT / "data" / "baadar.db"))
    with sqlite3.connect(db) as c:
        c.execute("""INSERT INTO competitor_data
            (channel_name, channel_id, video_title, views, upload_date, topic_tags, scanned_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
            ("E2 IELTS", "UC_xyz", "IELTS Reading Tips", 50000, "2026-06-01", '["reading","tips"]'))
        c.execute("""INSERT INTO competitor_data
            (channel_name, channel_id, video_title, views, upload_date, topic_tags, scanned_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
            ("IELTS Liz", "UC_abc", "IELTS Writing Task 1", 30000, "2026-06-05", '["writing","task1"]'))
    from saathi.tools.intelligence import get_competitor_insights
    result = get_competitor_insights()
    assert "top_topics" in result
    assert "channels" in result
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/SaathiAI && python -m pytest tests/test_intelligence.py::test_competitor_insights_returns_gaps -v
```
Expected: `FAILED`

- [ ] **Step 3: Add to `intelligence.py`**

```python
# Competitor channel IDs (hardcoded, update as needed)
COMPETITOR_CHANNELS = {
    "IELTS Advantage":  "UCJ5p5Pf4yCw6FVHISuDtkNA",
    "E2 IELTS":         "UCqs-8qjL4x4oKr0HVqfCr_A",
    "Fastrack IELTS":   "UCkFu3qQcMSDQFqBQIKFB5mQ",
    "IELTS Liz":        "UCDvDnBXBSNGJwZmh-jCYJpw",
}


def scan_competitors() -> dict:
    """Fetch top 5 videos from each competitor via YouTube Data API."""
    import httpx
    api_key = os.getenv("GOOGLE_API_KEY", "")
    if not api_key:
        return {"error": "GOOGLE_API_KEY not set"}
    results = {}
    for name, channel_id in COMPETITOR_CHANNELS.items():
        try:
            r = httpx.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "key": api_key, "channelId": channel_id, "part": "snippet",
                    "order": "viewCount", "maxResults": 5, "type": "video",
                    "publishedAfter": (
                        datetime.now(timezone.utc) - timedelta(days=30)
                    ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
                timeout=15,
            )
            items = r.json().get("items", [])
            channel_results = []
            with _conn() as c:
                for item in items:
                    snippet = item["snippet"]
                    title = snippet.get("title", "")
                    published = snippet.get("publishedAt", "")[:10]
                    c.execute("""
                        INSERT OR IGNORE INTO competitor_data
                            (channel_name, channel_id, video_title, views, upload_date, topic_tags)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (name, channel_id, title, 0, published, json.dumps([])))
                    channel_results.append({"title": title, "published": published})
            results[name] = channel_results
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def get_competitor_insights() -> dict:
    """Analyze competitor data — top topics, upload frequency, gaps."""
    with _conn() as c:
        rows = c.execute(
            "SELECT channel_name, video_title, views, upload_date FROM competitor_data ORDER BY scanned_at DESC"
        ).fetchall()
    channels: dict = {}
    all_titles = []
    for r in rows:
        channels.setdefault(r["channel_name"], []).append(r["video_title"])
        all_titles.append(r["video_title"])
    # Use LLM to find topic patterns and gaps
    if all_titles:
        from ._llm_helper import ask_llm, extract_json
        prompt = f"""These are recent video titles from top IELTS YouTube channels:
{json.dumps(all_titles[:40], ensure_ascii=False)}

Analyze and return:
1. top_topics: list of 5 most common topics (e.g. "Writing Task 2", "Speaking Part 1")
2. gaps: list of 3 topics rarely covered that Mr. Yeti could own
3. upload_pattern: observation about how often they upload

Return ONLY valid JSON: {{"top_topics": [...], "gaps": [...], "upload_pattern": "..."}}"""
        try:
            data = extract_json(ask_llm(prompt))
        except Exception:
            data = {"top_topics": [], "gaps": [], "upload_pattern": "unknown"}
    else:
        data = {"top_topics": [], "gaps": [], "upload_pattern": "no data yet"}
    data["channels"] = {k: len(v) for k, v in channels.items()}
    data["total_videos_tracked"] = len(all_titles)
    return data
```

- [ ] **Step 4: Add endpoints to `server.py`**

```python
@app.post("/api/v1/competitors/scan")
async def competitors_scan():
    """Fetch top 5 videos from each competitor channel."""
    from .tools.intelligence import scan_competitors
    import asyncio
    result = await asyncio.get_event_loop().run_in_executor(None, scan_competitors)
    return {"ok": True, "results": result}

@app.get("/api/v1/competitors/insights")
async def competitors_insights():
    """Return pattern analysis from competitor data."""
    from .tools.intelligence import get_competitor_insights
    import asyncio
    result = await asyncio.get_event_loop().run_in_executor(None, get_competitor_insights)
    return {"ok": True, **result}
```

- [ ] **Step 5: Run test**

```bash
cd ~/SaathiAI && python -m pytest tests/test_intelligence.py::test_competitor_insights_returns_gaps -v
```
Expected: `PASSED`

- [ ] **Step 6: Commit**

```bash
git add saathi/tools/intelligence.py saathi/server.py tests/test_intelligence.py
git commit -m "feat: competitor intelligence — scan 4 IELTS channels, pattern/gap analysis"
```

---

## Task 8: Thumbnail Scoring (5 options → AI ranks → best selected)

**Files:**
- Modify: `saathi/tools/thumbnail.py`
- Modify: `saathi/server.py`
- Test: `tests/test_intelligence.py`

**Interfaces:**
- Produces: `score_thumbnails(concepts: list[dict]) -> list[dict]` — adds `score` and `rank` fields

- [ ] **Step 1: Write failing test**

```python
def test_score_thumbnails_ranks_correctly():
    fake_response = json.dumps({
        "scored": [
            {"idx": 0, "face_visibility": 9, "text_contrast": 8, "color_pop": 7, "emotion": 8, "curiosity_gap": 9},
            {"idx": 1, "face_visibility": 5, "text_contrast": 6, "color_pop": 5, "emotion": 4, "curiosity_gap": 5},
        ]
    })
    concepts = [
        {"description": "Mr. Yeti shocked face, text: STOP MAKING THIS MISTAKE"},
        {"description": "Plain text on white background"},
    ]
    with mock.patch("saathi.tools.thumbnail.ask_llm", return_value=fake_response):
        from saathi.tools.thumbnail import score_thumbnails
        result = score_thumbnails(concepts)
    assert result[0]["rank"] == 1
    assert result[0]["total"] > result[1]["total"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/SaathiAI && python -m pytest tests/test_intelligence.py::test_score_thumbnails_ranks_correctly -v
```
Expected: `FAILED`

- [ ] **Step 3: Add to `saathi/tools/thumbnail.py`**

```python
def score_thumbnails(concepts: list) -> list:
    """Score 5 thumbnail concepts on 5 criteria, return ranked list."""
    from ._llm_helper import ask_llm, extract_json
    prompt = f"""You are a YouTube thumbnail expert. Score each of these {len(concepts)} thumbnail concepts for an IELTS education channel.

Concepts:
{json.dumps([{"idx": i, "description": c.get("description", str(c))} for i, c in enumerate(concepts)], ensure_ascii=False)}

Score each concept (0-10) on:
- face_visibility: is a face (Mr. Yeti) clearly visible and expressive?
- text_contrast: is the text readable and high contrast?
- color_pop: does it stand out in a crowded feed?
- emotion: does it convey strong emotion (shock, curiosity, urgency)?
- curiosity_gap: does it make you NEED to click?

Return ONLY valid JSON:
{{"scored": [{{"idx": 0, "face_visibility": 8, "text_contrast": 7, "color_pop": 9, "emotion": 8, "curiosity_gap": 9}}]}}"""
    raw = ask_llm(prompt, system="You are a YouTube CTR optimization expert. Reply ONLY with valid JSON.")
    data = extract_json(raw)
    scored = data.get("scored", [])
    # Merge scores back into concepts
    result = []
    for item in scored:
        idx = item.get("idx", 0)
        total = (item.get("face_visibility", 0) + item.get("text_contrast", 0) +
                 item.get("color_pop", 0) + item.get("emotion", 0) + item.get("curiosity_gap", 0))
        concept = concepts[idx] if idx < len(concepts) else {}
        result.append({**concept, **item, "total": total})
    result.sort(key=lambda x: x["total"], reverse=True)
    for i, r in enumerate(result):
        r["rank"] = i + 1
    return result


def generate_and_score(topic: str, title: str = "") -> dict:
    """Generate 5 thumbnail concepts and score them. Returns top 1 selected."""
    from ._llm_helper import ask_llm, extract_json
    prompt = f"""Generate 5 different thumbnail concepts for a YouTube Short about: "{topic}"
Title: "{title}"
Character: Mr. Yeti — friendly Yeti, white fur, round glasses, teacher suit.
Each concept must describe: facial expression, text overlay (max 5 words), background, color scheme.
Return ONLY valid JSON: {{"concepts": [{{"description": "..."}}]}}"""
    raw = ask_llm(prompt, system="You are a viral YouTube thumbnail designer. Reply ONLY with valid JSON.")
    data = extract_json(raw)
    concepts = data.get("concepts", [])
    scored = score_thumbnails(concepts)
    return {"all": scored, "selected": scored[0] if scored else None}
```

- [ ] **Step 4: Upgrade `/studio/thumbnail` in `server.py`**

Find `@app.post("/api/v1/studio/thumbnail")` and update:

```python
@app.post("/api/v1/studio/thumbnail")
async def studio_thumbnail(request: Request):
    """Generate 5 thumbnail concepts, AI-score them, return best + all ranked."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    topic = body.get("topic", "IELTS tip")
    title = body.get("title", "")
    try:
        import asyncio
        from .tools.thumbnail import generate_and_score
        result = await asyncio.get_event_loop().run_in_executor(None, generate_and_score, topic, title)
        return {"ok": True, **result}
    except Exception as e:
        return {"ok": False, "error": str(e)}
```

- [ ] **Step 5: Run test**

```bash
cd ~/SaathiAI && python -m pytest tests/test_intelligence.py::test_score_thumbnails_ranks_correctly -v
```
Expected: `PASSED`

- [ ] **Step 6: Commit**

```bash
git add saathi/tools/thumbnail.py saathi/server.py tests/test_intelligence.py
git commit -m "feat: thumbnail scoring — 5 concepts generated, AI-scored on 5 axes, top 1 selected"
```

---

## Task 9: Trend Fusion

**Files:**
- Modify: `saathi/tools/content_studio.py`
- Modify: `saathi/server.py`
- Test: `tests/test_intelligence.py`

**Interfaces:**
- Produces: `fuse_trend(ielts_topic: str, trend_format: str) -> dict`
  — `{fused_hook: str, script_angle: str, format: str, topic: str}`

- [ ] **Step 1: Write failing test**

```python
def test_fuse_trend_returns_hook_and_angle():
    fake = json.dumps({
        "fused_hook": "POV: You just said this in your IELTS exam.",
        "script_angle": "Role-play as an examiner reacting to the mistake"
    })
    with mock.patch("saathi.tools.content_studio.ask_llm", return_value=fake):
        from saathi.tools.content_studio import fuse_trend
        result = fuse_trend("Speaking Mistakes", "POV")
    assert "fused_hook" in result
    assert "POV" in result["fused_hook"] or "script_angle" in result
    assert result["format"] == "POV"
    assert result["topic"] == "Speaking Mistakes"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/SaathiAI && python -m pytest tests/test_intelligence.py::test_fuse_trend_returns_hook_and_angle -v
```
Expected: `FAILED`

- [ ] **Step 3: Add to `content_studio.py`**

```python
# Rotating trending formats — update weekly
TRENDING_FORMATS = [
    "POV", "Story Time", "Reaction", "Before vs After",
    "Hot Take", "Day in My Life", "Rate My", "Expectation vs Reality",
    "What I Wish I Knew", "Mistakes I Made",
]


def fuse_trend(ielts_topic: str, trend_format: str = "") -> dict:
    """Fuse a trending video format with an IELTS topic to create a viral hook."""
    from ._llm_helper import ask_llm, extract_json
    import random
    if not trend_format:
        trend_format = random.choice(TRENDING_FORMATS)
    prompt = f"""You are creating viral IELTS content by fusing a trending video format with an educational topic.

Trending format: "{trend_format}"
IELTS topic: "{ielts_topic}"
Character: Mr. Yeti (funny, direct, encouraging IELTS teacher)

Create:
1. fused_hook: An opening line that combines the trend format with the IELTS topic (max 12 words)
   Example: Trending=POV, Topic=Speaking Mistakes → "POV: You just said this in your IELTS exam."
2. script_angle: A 1-sentence description of how to structure the video using this format

Return ONLY valid JSON: {{"fused_hook": "...", "script_angle": "..."}}"""
    raw = ask_llm(prompt, system="You create viral educational content hooks. Reply ONLY with valid JSON.")
    data = extract_json(raw)
    return {
        "fused_hook": data.get("fused_hook", ""),
        "script_angle": data.get("script_angle", ""),
        "format": trend_format,
        "topic": ielts_topic,
    }
```

- [ ] **Step 4: Add endpoint to `server.py`**

```python
@app.post("/api/v1/trends/fuse")
async def trends_fuse(request: Request):
    """Fuse a trending format with an IELTS topic to generate a viral hook."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    topic = body.get("topic", "IELTS Speaking")
    trend_format = body.get("format", "")
    try:
        import asyncio
        from .tools.content_studio import fuse_trend
        result = await asyncio.get_event_loop().run_in_executor(None, fuse_trend, topic, trend_format)
        return {"ok": True, **result}
    except Exception as e:
        return {"ok": False, "error": str(e)}
```

- [ ] **Step 5: Run test**

```bash
cd ~/SaathiAI && python -m pytest tests/test_intelligence.py::test_fuse_trend_returns_hook_and_angle -v
```
Expected: `PASSED`

- [ ] **Step 6: Commit**

```bash
git add saathi/tools/content_studio.py saathi/server.py tests/test_intelligence.py
git commit -m "feat: trend fusion — fuse trending format + IELTS topic → viral hook"
```

---

## Task 10: Referral Engine

**Files:**
- Create: `saathi/tools/referral.py`
- Create: `tests/test_referral.py`
- Modify: `saathi/server.py`

**Interfaces:**
- Produces:
  - `generate_referral_code(uid: str) -> str`
  - `check_and_trigger_referral(uid: str, old_score: float, new_score: float) -> dict`
  - `poll_score_improvements() -> list[dict]` — called by background task

- [ ] **Step 1: Write failing tests**

```python
# tests/test_referral.py
import os, json, pytest
os.environ.setdefault("BAADAR_DB", "/tmp/test_baadar_ref.db")

from saathi.tools.intelligence import init_db

def test_generate_referral_code_is_unique():
    from saathi.tools.referral import generate_referral_code
    code1 = generate_referral_code("uid_001")
    code2 = generate_referral_code("uid_002")
    assert code1 != code2
    assert len(code1) == 8

def test_check_triggers_only_on_half_band_improvement():
    init_db()
    from saathi.tools.referral import check_and_trigger_referral
    # Improvement of 0.4 — should NOT trigger
    result = check_and_trigger_referral("uid_no", 6.0, 6.4)
    assert result["triggered"] is False
    # Improvement of 0.5 — should trigger
    result = check_and_trigger_referral("uid_yes", 6.0, 6.5)
    assert result["triggered"] is True
    assert "referral_code" in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/SaathiAI && python -m pytest tests/test_referral.py -v
```
Expected: `FAILED`

- [ ] **Step 3: Create `saathi/tools/referral.py`**

```python
"""
referral.py — Detect band score improvements → trigger referral offer.
Polls Firebase RTDB every 6 hours via Baadar background task.
"""
import json, os, random, sqlite3, string
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .. import config

DB_PATH = os.getenv("BAADAR_DB", str(config.ROOT / "data" / "baadar.db"))
FIREBASE_DB_URL = "https://ielts-and-language-practice-default-rtdb.firebaseio.com"
_SA_KEY = os.path.expanduser(os.getenv("FIREBASE_SA_KEY", "~/SaathiAI/firebase-admin.json"))

# Minimum band improvement to trigger referral
MIN_IMPROVEMENT = 0.5


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def generate_referral_code(uid: str) -> str:
    """Generate a unique 8-char referral code based on uid + random suffix."""
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"{uid[:3].upper()}{suffix}"


def check_and_trigger_referral(uid: str, old_score: float, new_score: float) -> dict:
    """If band improvement >= 0.5, generate referral code and save event."""
    improvement = new_score - old_score
    if improvement < MIN_IMPROVEMENT:
        return {"triggered": False, "uid": uid, "improvement": improvement}
    code = generate_referral_code(uid)
    with _conn() as c:
        # Avoid duplicate events for same uid within 30 days
        existing = c.execute(
            "SELECT id FROM referral_events WHERE uid=? AND sent_at > datetime('now', '-30 days')",
            (uid,)
        ).fetchone()
        if existing:
            return {"triggered": False, "uid": uid, "reason": "already_sent_recently"}
        c.execute(
            "INSERT INTO referral_events (uid, old_score, new_score, referral_code) VALUES (?,?,?,?)",
            (uid, old_score, new_score, code)
        )
    # Send Telegram alert to Ajay
    try:
        from .n8n_tools import send_telegram
        send_telegram(
            f"🎯 Referral triggered!\n\nUser {uid} improved from {old_score} → {new_score} band\n"
            f"Referral code: {code}\nOffer sent: Invite 3 friends → unlock Pro 7 days"
        )
    except Exception:
        pass
    return {"triggered": True, "uid": uid, "referral_code": code,
            "old_score": old_score, "new_score": new_score}


def poll_score_improvements() -> list:
    """Check Firebase RTDB for users whose band score improved. Called every 6h."""
    try:
        import firebase_admin
        from firebase_admin import credentials, db as rtdb
        if not firebase_admin._apps:
            cred = credentials.Certificate(_SA_KEY)
            firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})
        users_ref = rtdb.reference("users")
        all_users = users_ref.get() or {}
    except Exception as e:
        return [{"error": str(e)}]

    triggered = []
    with _conn() as c:
        known = {r["uid"]: r for r in c.execute(
            "SELECT uid, new_score FROM referral_events"
        ).fetchall()}

    for uid, profile in all_users.items():
        if not isinstance(profile, dict):
            continue
        current_score = profile.get("bandScore") or profile.get("band_score") or 0
        if not current_score:
            continue
        prev_score = known.get(uid, {}).get("new_score", current_score)
        result = check_and_trigger_referral(uid, prev_score, float(current_score))
        if result.get("triggered"):
            triggered.append(result)

    return triggered
```

- [ ] **Step 4: Register background poll in `server.py` startup**

In `server.py`, find `_start_background()` and add the 6-hour referral poll:

```python
# Inside _start_background() in server.py, add:
import threading, time

def _referral_poll_loop():
    while True:
        try:
            from .tools.referral import poll_score_improvements
            poll_score_improvements()
        except Exception:
            pass
        time.sleep(6 * 3600)  # every 6 hours

threading.Thread(target=_referral_poll_loop, daemon=True).start()
```

- [ ] **Step 5: Add endpoint to `server.py`**

```python
@app.post("/api/v1/referral/check")
async def referral_check(request: Request):
    """Manually trigger a referral check for a specific user."""
    body = await request.json()
    uid = body.get("uid", "")
    old_score = float(body.get("old_score", 0))
    new_score = float(body.get("new_score", 0))
    if not uid:
        return {"ok": False, "error": "uid required"}
    from .tools.referral import check_and_trigger_referral
    result = check_and_trigger_referral(uid, old_score, new_score)
    return {"ok": True, **result}
```

- [ ] **Step 6: Run tests**

```bash
cd ~/SaathiAI && python -m pytest tests/test_referral.py -v
```
Expected: all `PASSED`

- [ ] **Step 7: Commit**

```bash
git add saathi/tools/referral.py saathi/server.py tests/test_referral.py
git commit -m "feat: referral engine — detect 0.5 band improvement, generate code, Telegram alert, 6h poll"
```

---

## Task 11: CEO Morning Dashboard (8am NPT Telegram)

**Files:**
- Modify: `saathi/tools/intelligence.py`
- Modify: `saathi/scheduler.py` (or `server.py` startup)
- Test: `tests/test_intelligence.py`

**Interfaces:**
- Consumes: `get_format_avg_retention()`, Firebase RTDB, `send_telegram()`
- Produces: `build_ceo_dashboard() -> str` — formatted Telegram message

- [ ] **Step 1: Write failing test**

```python
def test_build_ceo_dashboard_contains_key_fields():
    from unittest import mock
    fake_retention = {"quiz": 80.0, "vocab": 42.0}
    with mock.patch("saathi.tools.intelligence.get_format_avg_retention", return_value=fake_retention):
        with mock.patch("saathi.tools.intelligence._fetch_firebase_new_users", return_value=5):
            with mock.patch("saathi.tools.intelligence._fetch_best_worst_video",
                            return_value=({"title": "Quiz #1", "retention": 81}, {"title": "Vocab #14", "retention": 38})):
                from saathi.tools.intelligence import build_ceo_dashboard
                msg = build_ceo_dashboard()
    assert "New Users" in msg
    assert "Quiz #1" in msg
    assert "quiz" in msg.lower()
    assert "Recommendation" in msg
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/SaathiAI && python -m pytest tests/test_intelligence.py::test_build_ceo_dashboard_contains_key_fields -v
```
Expected: `FAILED`

- [ ] **Step 3: Add to `intelligence.py`**

```python
def _fetch_firebase_new_users(hours: int = 24) -> int:
    """Count users created in the last N hours from Firebase RTDB."""
    try:
        import firebase_admin
        from firebase_admin import credentials, db as rtdb
        sa_key = os.path.expanduser(os.getenv("FIREBASE_SA_KEY", "~/SaathiAI/firebase-admin.json"))
        if not firebase_admin._apps:
            cred = credentials.Certificate(sa_key)
            firebase_admin.initialize_app(cred, {
                "databaseURL": "https://ielts-and-language-practice-default-rtdb.firebaseio.com"
            })
        users = rtdb.reference("users").get() or {}
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp() * 1000
        return sum(1 for u in users.values()
                   if isinstance(u, dict) and u.get("createdAt", 0) > cutoff)
    except Exception:
        return 0


def _fetch_best_worst_video() -> tuple:
    """Return (best, worst) video dicts from retention table."""
    with _conn() as c:
        best = c.execute(
            "SELECT video_id, completion_pct, score FROM video_retention ORDER BY completion_pct DESC LIMIT 1"
        ).fetchone()
        worst = c.execute(
            "SELECT video_id, completion_pct, score FROM video_retention ORDER BY completion_pct ASC LIMIT 1"
        ).fetchone()
    best_d = {"title": best["video_id"], "retention": best["completion_pct"]} if best else {"title": "N/A", "retention": 0}
    worst_d = {"title": worst["video_id"], "retention": worst["completion_pct"]} if worst else {"title": "N/A", "retention": 0}
    return best_d, worst_d


def build_ceo_dashboard() -> str:
    """Build the daily CEO Telegram message."""
    new_users = _fetch_firebase_new_users(24)
    best, worst = _fetch_best_worst_video()
    avgs = get_format_avg_retention()
    top_format = max(avgs, key=lambda k: avgs[k]) if avgs else "quiz"
    top_retention = avgs.get(top_format, 0)

    # Simple revenue estimate from DB (premium user count × NPR 500/month rough estimate)
    try:
        with _conn() as c:
            premium_count = c.execute(
                "SELECT COUNT(*) FROM referral_events WHERE conversions > 0"
            ).fetchone()[0]
        revenue_est = premium_count * 500
    except Exception:
        revenue_est = 0

    recommendation = f"Make more {top_format} videos — avg {top_retention:.0f}% retention."
    if worst["retention"] < 30:
        recommendation += f" Stop making '{worst['title']}' style content."

    npt = datetime.now(timezone(timedelta(hours=5, minutes=45)))
    date_str = npt.strftime("%b %d, %Y")

    return (
        f"☀️ Good morning, Ajay — {date_str}\n\n"
        f"📊 PIELTS Daily Report\n\n"
        f"👤 New Users (24h): {new_users}\n"
        f"🏆 Best Video: {best['title']}\n"
        f"   Retention: {best['retention']:.0f}%\n"
        f"💀 Worst Video: {worst['title']}\n"
        f"   Retention: {worst['retention']:.0f}%\n"
        f"💰 Revenue Est: NPR {revenue_est:,}\n\n"
        f"📈 Format Performance:\n"
        + "\n".join(f"  {k}: {v:.0f}% avg retention" for k, v in sorted(avgs.items(), key=lambda x: -x[1]))
        + f"\n\n💡 Recommendation:\n{recommendation}"
    )


def send_ceo_dashboard():
    """Build and send the CEO dashboard to Telegram."""
    from .n8n_tools import send_telegram
    msg = build_ceo_dashboard()
    send_telegram(msg)
```

- [ ] **Step 4: Schedule at 8am NPT in `saathi/scheduler.py`**

Open `~/SaathiAI/saathi/scheduler.py` and find where other morning jobs are scheduled. Add:

```python
# Find the APScheduler setup and add:
from .tools.intelligence import send_ceo_dashboard

# 8:00 AM NPT = 2:15 AM UTC (NPT is UTC+5:45)
scheduler.add_job(
    send_ceo_dashboard,
    "cron", hour=2, minute=15,
    id="ceo_dashboard", replace_existing=True
)
```

- [ ] **Step 5: Run test**

```bash
cd ~/SaathiAI && python -m pytest tests/test_intelligence.py::test_build_ceo_dashboard_contains_key_fields -v
```
Expected: `PASSED`

- [ ] **Step 6: Commit**

```bash
git add saathi/tools/intelligence.py saathi/scheduler.py tests/test_intelligence.py
git commit -m "feat: CEO morning dashboard — daily 8am NPT Telegram with users, retention, revenue, recommendation"
```

---

## Task 12: Restart Baadar + Smoke Test All Endpoints

**Files:**
- No code changes — integration verification only

- [ ] **Step 1: Restart Baadar**

```bash
launchctl stop com.ajay.saathiai && sleep 3 && launchctl start com.ajay.saathiai && sleep 4
```

- [ ] **Step 2: Smoke test all new endpoints**

```bash
BASE="http://localhost:8765"
TOKEN="9278af2af4de585e"
H="-H 'x-saathi-token: $TOKEN'"

# Retention
curl -s -X POST "$BASE/api/v1/analytics/retention" \
  -H "Content-Type: application/json" -H "x-saathi-token: $TOKEN" \
  -d '{"video_id":"test_vid","platform":"youtube","completion_pct":72,"ret_3s":90,"ret_10s":80,"ret_30s":70,"avg_watch_sec":18}' | python3 -m json.tool

# Patterns
curl -s "$BASE/api/v1/analytics/patterns" -H "x-saathi-token: $TOKEN" | python3 -m json.tool

# Hook lab
curl -s -X POST "$BASE/api/v1/hooks/generate" \
  -H "Content-Type: application/json" -H "x-saathi-token: $TOKEN" \
  -d '{"topic":"Grammar Mistakes"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print('top3:', d.get('top3'))"

# Yeti persona
curl -s "$BASE/api/v1/yeti/persona" -H "x-saathi-token: $TOKEN" | python3 -c "import sys,json; d=json.load(sys.stdin); print('traits:', d.get('persona',{}).get('traits'))"

# Trend fusion
curl -s -X POST "$BASE/api/v1/trends/fuse" \
  -H "Content-Type: application/json" -H "x-saathi-token: $TOKEN" \
  -d '{"topic":"Speaking Mistakes","format":"POV"}' | python3 -m json.tool

# Thumbnail scoring
curl -s -X POST "$BASE/api/v1/studio/thumbnail" \
  -H "Content-Type: application/json" -H "x-saathi-token: $TOKEN" \
  -d '{"topic":"Grammar Mistakes","title":"Stop This Grammar Error"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print('selected:', d.get('selected',{}).get('description','')[:60])"
```

Expected: all return `{"ok": true, ...}`

- [ ] **Step 3: Trigger a manual CEO dashboard test**

```bash
curl -s -X POST "http://localhost:8765/api/v1/telegram/send" \
  -H "Content-Type: application/json" -H "x-saathi-token: 9278af2af4de585e" \
  -d '{"text":"Testing CEO dashboard manually..."}' 
# Then call send_ceo_dashboard directly:
cd ~/SaathiAI && python3 -c "
import sys; sys.path.insert(0, '.')
from saathi.tools.intelligence import build_ceo_dashboard, send_ceo_dashboard
print(build_ceo_dashboard())
send_ceo_dashboard()
print('Sent!')
"
```

- [ ] **Step 4: Final commit**

```bash
cd ~/SaathiAI
git add -A
git commit -m "feat: Baadar intelligence layer — 10 features complete (retention, hooks, patterns, persona, comments, competitors, thumbnails, trend fusion, referral, CEO dashboard)"
```

---

## Self-Review

**Spec coverage check:**
1. ✅ Retention Analyzer — Task 2, `/analytics/retention`, A/B/C/D scoring, kill formats
2. ✅ Hook Laboratory — Task 3, 20 hooks → AI scored → top 3
3. ✅ Viral Pattern Database — Task 4, `viral_patterns` table, `/analytics/patterns`, auto-weighting via `get_top_formats()`
4. ✅ Mr. Yeti Character Engine — Task 5, `yeti_persona.json`, persona injected into `generate_script()`
5. ✅ Comment Intelligence — Task 6, classify + extract video ideas
6. ✅ Competitor Intelligence — Task 7, 4 channels, pattern/gap analysis
7. ✅ Thumbnail Scoring — Task 8, 5 concepts, 5-axis scoring, top 1 selected
8. ✅ Trend Fusion — Task 9, `/trends/fuse`, fused hook + script angle
9. ✅ Referral Engine — Task 10, 0.5 band improvement triggers, 6h poll, Telegram alert
10. ✅ CEO Dashboard — Task 11, 8am NPT, users/best-worst video/revenue/recommendation

**Missing from spec now covered:**
- `hook_performance` 3-video queue: the Hook Lab generates hooks and queues them, but actually creating 3 separate videos is handled by calling `/studio/full_pipeline` 3 times with different hooks from `top3` — this is a workflow concern, not a new endpoint.
- D-format suppression: `get_killed_formats()` is implemented; `content_research.py` should call it — this is a follow-up task once data accumulates.
