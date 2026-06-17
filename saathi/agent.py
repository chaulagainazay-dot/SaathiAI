"""SaathiAI agent core — tool-use loop with memory.

Two interchangeable brains:
  - Gemini (free tier) via its OpenAI-compatible endpoint  ← default if GOOGLE_API_KEY set
  - Claude via the Anthropic API
"""
import json
from pathlib import Path

from . import config
from . import activity
from .persona import SYSTEM_PROMPT
from .memory import Memory
from .tools.registry import TOOL_SCHEMAS, execute_tool

# ---------- Suna-style skills + memory loader ----------

_SKILLS_DIR = Path(__file__).parent / "skills"
_MEMORY_DIR = Path(__file__).parent / "memory"

# keyword → skill folder name (order = priority — first match wins)
_SKILL_ROUTES = {
    "deep-research": [
        "search for", "research", "look up", "check online",
        "youtube info", "youtube subtitles", "github", "rss feed",
        "news about", "what is", "who is", "how does", "tell me about",
        "find information", "find out",
    ],
    "canteen-ops": [
        "canteen", "hcg", "hcgms", "sajana", "yabesh", "hasina",
        "aayush", "nishant", "revenue", "sales", "credit", "report",
        "hygiene", "npr", "daily summary", "target",
    ],
    "ielts-teaching": [
        "ielts", "band score", "writing task", "speaking part",
        "listening section", "reading task", "essay", "ielts vocabulary",
        "ielts grammar", "general training", "task 1", "task 2",
    ],
    "content-creation": [
        "post", "caption", "script", "story", "facebook", "instagram",
        "youtube", "reel", "short video", "blog post", "content", "yeti",
        "mr yeti", "publish", "write for", "draft a", "generate a post",
    ],
}


def _load_skill(user_text: str) -> str:
    """Return the SKILL.md content for the best-matching skill, or ''.
    Uses score-based matching (most keyword hits wins) to handle overlap."""
    text = user_text.lower()
    best_skill, best_score = None, 0
    for skill_name, keywords in _SKILL_ROUTES.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score, best_skill = score, skill_name
    if best_skill and best_score > 0:
        skill_file = _SKILLS_DIR / best_skill / "SKILL.md"
        if skill_file.exists():
            return skill_file.read_text(encoding="utf-8")[:1500]
    return ""


def _load_memory() -> str:
    """Return a compact project-memory block from saathi/memory/*.md.
    Keep under 400 chars per file to stay within Groq's 12k TPM limit."""
    if not _MEMORY_DIR.exists():
        return ""
    parts = []
    for name in ("conventions.md", "decisions.md"):
        f = _MEMORY_DIR / name
        if f.exists():
            parts.append(f"## {name}\n" + f.read_text(encoding="utf-8")[:400])
    return "\n\n".join(parts)

MAX_TOOL_ITERATIONS = 8


# Tools that are always sent (core actions every request might need)
_CORE_TOOLS = {
    "remember_fact", "manage_tasks", "record_feedback",
    "look_at_screen", "check_messages", "run_shell",
}

# Keyword → tool names to add for that context
_TOOL_ROUTES: dict[str, set[str]] = {
    "content": {"draft_social_content", "stage_draft", "post_social_content",
                "post_to_all_socials", "make_content", "todays_content",
                "make_video", "send_video_to_phone", "make_flow_prompts",
                "make_talking_yeti", "make_animated_video", "check_animated_video",
                "make_daily_kit", "publish_blog", "make_blog_post",
                "queue_video", "publish_to_youtube", "list_social_connections"},
    "canteen": {"canteen_query"},
    "research": {"web_search", "read_webpage", "youtube_info", "youtube_subtitles",
                 "github_repo", "rss_feed", "bilibili_search", "research",
                 "deep_plan", "reach_doctor",
                 "crypto_prices", "motivational_quote", "exchange_rate"},
    "mac":     {"mac_open_app", "mac_close_app", "mac_run_shortcut",
                "mac_type_text", "applescript", "my_files", "search_mac_files",
                "read_mac_file", "write_file", "get_mobile_link"},
    "project": {"project_overview", "read_project_file", "search_project",
                "list_projects", "plan_project_work", "project_run",
                "project_edit_file", "register_project"},
    "comms":   {"send_email", "check_email", "send_telegram",
                "add_reminder", "list_reminders", "todays_events", "add_event",
                "find_community_questions", "ask_document"},
    "health":  {"system_health", "performance_report", "self_improve",
                "self_status", "what_learned"},
    "nepali":  {"teach_nepali", "nepali_progress",
                "english_log_mistake", "english_progress"},
    "n8n":     {"trigger_n8n_workflow"},
}

_ALL_TOOL_NAMES = {t["name"] for t in TOOL_SCHEMAS}


def _select_tools(user_text: str) -> list[dict]:
    """Send only tools relevant to this request to stay under Groq's TPM limit."""
    text = user_text.lower()
    selected = set(_CORE_TOOLS)

    kw_map = {
        "content": ["post", "caption", "script", "story", "facebook", "instagram",
                    "youtube", "reel", "blog", "content", "yeti", "mr yeti",
                    "publish", "draft", "generate", "write", "video", "kit"],
        "canteen": ["canteen", "hcg", "hcgms", "sajana", "yabesh", "hasina",
                    "aayush", "nishant", "revenue", "sales", "credit", "report",
                    "hygiene", "npr", "daily summary", "target"],
        "research": ["search", "research", "look up", "find", "youtube info",
                     "github", "rss", "news", "what is", "who is", "how does",
                     "webpage", "url", "website", "bilibili",
                     "crypto", "bitcoin", "ethereum", "price", "exchange rate",
                     "npr", "usd", "convert", "quote", "motivation"],
        "mac":     ["open", "close", "type", "screen", "file", "folder",
                    "shortcut", "mac", "desktop", "app"],
        "project": ["project", "code", "pielts", "hcgms", "build", "fix bug",
                    "deploy", "git"],
        "comms":   ["email", "telegram", "reminder", "event", "calendar",
                    "message", "send", "reddit", "quora"],
        "health":  ["health", "status", "performance", "learn", "improve",
                    "self improve", "self status"],
        "nepali":  ["nepali", "english coach", "practice", "correction"],
        "n8n":     ["n8n", "workflow", "automate"],
    }

    for group, keywords in kw_map.items():
        if any(kw in text for kw in keywords):
            selected |= _TOOL_ROUTES.get(group, set())

    # If nothing matched beyond core, send content + research as safe defaults
    if selected == set(_CORE_TOOLS):
        selected |= _TOOL_ROUTES["content"] | _TOOL_ROUTES["research"]

    # Filter to only tools that actually exist in registry
    selected &= _ALL_TOOL_NAMES

    tool_map = {t["name"]: t for t in TOOL_SCHEMAS}
    return [{
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["input_schema"],
        },
    } for name in selected if (t := tool_map.get(name))]


def _openai_tools() -> list[dict]:
    """Convert all tool schemas — used for non-Groq providers."""
    return [{
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["input_schema"],
        },
    } for t in TOOL_SCHEMAS]


class SaathiAgent:
    def __init__(self):
        self.memory = Memory(config.DB_PATH)
        self.provider = config.LLM_PROVIDER
        if self.provider == "groq":
            from openai import OpenAI
            self.client = OpenAI(api_key=config.GROQ_API_KEY,
                                 base_url="https://api.groq.com/openai/v1")
            self.model = config.GROQ_MODEL
        elif self.provider == "gemini":
            from openai import OpenAI
            self.client = OpenAI(
                api_key=config.GOOGLE_API_KEY,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            )
            self.model = config.GEMINI_MODEL
        elif self.provider == "ollama":
            from openai import OpenAI
            self.client = OpenAI(api_key="ollama", base_url=config.OLLAMA_URL)
            self.model = config.OLLAMA_MODEL
        else:
            import anthropic
            self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
            self.model = config.CLAUDE_MODEL

    def complete(self, system: str, prompt: str, max_tokens: int = 400) -> str:
        """One simple no-tools completion — used by the self-improvement engine."""
        if self.provider in ("gemini", "ollama", "groq"):
            resp = self._create_with_retry(
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": prompt}],
                max_tokens=max_tokens)
            return (resp.choices[0].message.content or "").strip()
        resp = self.client.messages.create(
            model=self.model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": prompt}])
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    # ---------- public ----------

    def respond(self, user_text: str, session_id: str = "default",
                speaker_verified: bool = False) -> str:
        # smaller context = faster replies; 6 turns + 4 facts is plenty for voice
        history = self.memory.recent_turns(session_id, limit=6)
        facts = self.memory.relevant_facts(user_text, limit=4)

        system = SYSTEM_PROMPT

        # Suna-style: inject project memory (conventions, decisions, overview)
        memory_ctx = _load_memory()
        if memory_ctx:
            system += f"\n\n<project-memory>\n{memory_ctx}\n</project-memory>"

        # Suna-style: inject task-specific skill
        skill_content = _load_skill(user_text)
        if skill_content:
            system += f"\n\n<skill>\n{skill_content}\n</skill>"

        if facts:
            system += "\n\n# Things you remember about Ajay\n" + "\n".join(f"- {f}" for f in facts)
        system += f"\n\n# Session\nSpeaker verified as Ajay: {speaker_verified}"

        activity.clear(session_id)
        activity.log(session_id, "start", "💭 Understanding your request…")
        if self.provider in ("gemini", "ollama", "groq"):
            reply = self._respond_openai(system, history, user_text, speaker_verified, session_id)
        else:
            reply = self._respond_anthropic(system, history, user_text, speaker_verified, session_id)
        activity.log(session_id, "done", "✅ Done")

        self.memory.save_turn(session_id, "user", user_text)
        self.memory.save_turn(session_id, "assistant", reply)
        self._learn_in_background(user_text, reply)
        return reply

    def _learn_in_background(self, user_text: str, reply: str):
        """Extract durable learnings from this exchange without blocking the reply."""
        import threading

        def task():
            try:
                from . import selfimprove
                selfimprove.learn_from_turn(user_text, reply)
            except Exception:
                pass

        threading.Thread(target=task, daemon=True).start()

    # ---------- Gemini (OpenAI-compatible) ----------

    FALLBACK_MODELS = ["gemini-2.5-flash"]

    def _create_with_retry(self, **kwargs):
        """Retry on transient free-tier errors (503 overload, 429 rate limit),
        falling back to alternate Gemini models if the primary stays busy."""
        import time
        from openai import APIStatusError
        if self.provider == "gemini":
            # only Gemini understands these alternate model names
            models = [self.model] + [m for m in self.FALLBACK_MODELS if m != self.model]
        else:
            # groq / ollama: one model, then provider-level fallback below
            models = [self.model]
        # Groq rate-limits on tokens/min — don't stall on long backoffs, fail
        # fast to the fallback brain so a reply still comes quickly.
        attempts, backoff = (2, 1.0) if self.provider == "groq" else (4, 3.0)
        last_err = None
        for model in models:
            for attempt in range(attempts):
                try:
                    return self.client.chat.completions.create(model=model, **kwargs)
                except APIStatusError as e:
                    # Groq's llama sometimes emits malformed tool-call syntax
                    # (400 tool_use_failed) — retrying usually fixes it
                    transient = (e.status_code in (429, 500, 503)
                                 or "tool_use_failed" in str(e))
                    if not transient:
                        raise
                    last_err = e
                    # "limit: 0" = model has no free quota; daily-quota errors
                    # won't recover by waiting — skip to next model/fallback
                    if "limit: 0" in str(e) or "PerDay" in str(e):
                        break
                    if attempt < attempts - 1:
                        time.sleep(backoff * (attempt + 1))
                except Exception as e:
                    # Network offline or DNS failure — go straight to Ollama
                    err_s = str(e).lower()
                    if any(k in err_s for k in ("connect", "network", "name or service",
                                                "nodename", "timeout", "unreachable")):
                        last_err = e
                        break  # skip remaining attempts, fall through to Ollama
                    raise
        # busy/exhausted/offline — fall back so a reply still comes.
        # Groq → Gemini (fast cloud) → local Ollama; Gemini → local Ollama.
        if self.provider == "groq" and config.GOOGLE_API_KEY:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=config.GOOGLE_API_KEY,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
                self.model = config.GEMINI_MODEL
                self.provider = "gemini"
                return self.client.chat.completions.create(model=self.model, **kwargs)
            except Exception:
                pass
        if self.provider in ("gemini", "groq"):
            try:
                self._fallback_to_ollama()
                return self.client.chat.completions.create(model=self.model, **kwargs)
            except Exception:
                pass
        raise last_err

    def _fallback_to_ollama(self):
        """When Gemini's free quota is exhausted, switch to the local brain."""
        import httpx
        from openai import OpenAI
        base = config.OLLAMA_URL.rsplit("/v1", 1)[0]
        httpx.get(base, timeout=3)  # raises if Ollama isn't running
        self.client = OpenAI(api_key="ollama", base_url=config.OLLAMA_URL)
        self.model = config.OLLAMA_MODEL
        self.provider = "ollama"

    def _respond_openai(self, system, history, user_text, speaker_verified,
                        session_id="default") -> str:
        messages = ([{"role": "system", "content": system}] + history +
                    [{"role": "user", "content": user_text}])
        # Groq has tight TPM limits — send only relevant tools to avoid 413 errors
        tools = _select_tools(user_text) if self.provider == "groq" else _openai_tools()
        for _ in range(MAX_TOOL_ITERATIONS):
            resp = self._create_with_retry(
                messages=messages, tools=tools, max_tokens=512)
            msg = resp.choices[0].message
            if not msg.tool_calls:
                text = (msg.content or "").strip()
                if text:
                    return text
                # model returned empty text after tool use — force a final answer
                messages.append({"role": "user",
                                 "content": "Summarize the tool result for Ajay in one "
                                            "short spoken sentence (his language)."})
                resp = self._create_with_retry(messages=messages, max_tokens=512)
                return (resp.choices[0].message.content or "Done.").strip()
            if (msg.content or "").strip():
                activity.log(session_id, "think", "💭 " + msg.content.strip()[:120])
            messages.append({"role": "assistant", "content": msg.content,
                             "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                activity.log_tool(session_id, tc.function.name, args)
                result = execute_tool(tc.function.name, args,
                                      speaker_verified=speaker_verified)
                activity.log_result(session_id, result)
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": json.dumps(result, ensure_ascii=False,
                                                       default=str)})
        return (msg.content or "I ran out of tool steps — try asking again.").strip()

    # ---------- Claude ----------

    def _respond_anthropic(self, system, history, user_text, speaker_verified,
                           session_id="default") -> str:
        messages = history + [{"role": "user", "content": user_text}]
        for _ in range(MAX_TOOL_ITERATIONS):
            resp = self.client.messages.create(
                model=self.model, max_tokens=512, system=system,
                tools=TOOL_SCHEMAS, messages=messages)
            if resp.stop_reason != "tool_use":
                break
            for block in resp.content:
                if block.type == "text" and block.text.strip():
                    activity.log(session_id, "think", "💭 " + block.text.strip()[:120])
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if block.type == "tool_use":
                    activity.log_tool(session_id, block.name, block.input)
                    result = execute_tool(block.name, block.input,
                                          speaker_verified=speaker_verified)
                    activity.log_result(session_id, result)
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": json.dumps(result, ensure_ascii=False,
                                                          default=str)})
            messages.append({"role": "user", "content": results})
        return "".join(b.text for b in resp.content if b.type == "text").strip()
