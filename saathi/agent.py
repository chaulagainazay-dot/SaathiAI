"""SaathiAI agent core — tool-use loop with memory.

Two interchangeable brains:
  - Gemini (free tier) via its OpenAI-compatible endpoint  ← default if GOOGLE_API_KEY set
  - Claude via the Anthropic API
"""
import json

from . import config
from .persona import SYSTEM_PROMPT
from .memory import Memory
from .tools.registry import TOOL_SCHEMAS, execute_tool

MAX_TOOL_ITERATIONS = 8


def _openai_tools() -> list[dict]:
    """Convert Anthropic-style tool schemas to OpenAI/Gemini function format."""
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
        if facts:
            system += "\n\n# Things you remember about Ajay\n" + "\n".join(f"- {f}" for f in facts)
        system += f"\n\n# Session\nSpeaker verified as Ajay: {speaker_verified}"

        if self.provider in ("gemini", "ollama", "groq"):
            reply = self._respond_openai(system, history, user_text, speaker_verified)
        else:
            reply = self._respond_anthropic(system, history, user_text, speaker_verified)

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
        if self.provider == "ollama":
            models = [self.model]  # local model — no cloud fallbacks
        else:
            models = [self.model] + [m for m in self.FALLBACK_MODELS if m != self.model]
        # Groq rate-limits on tokens/min — don't stall on long backoffs, fail
        # fast to the fallback brain so a reply still comes quickly.
        attempts, backoff = (2, 1.0) if self.provider == "groq" else (4, 3.0)
        last_err = None
        for model in models:
            for attempt in range(attempts):
                try:
                    return self.client.chat.completions.create(model=model, **kwargs)
                except APIStatusError as e:
                    if e.status_code not in (429, 500, 503):
                        raise
                    last_err = e
                    # "limit: 0" = model has no free quota; daily-quota errors
                    # won't recover by waiting — skip to next model/fallback
                    if "limit: 0" in str(e) or "PerDay" in str(e):
                        break
                    if attempt < attempts - 1:
                        time.sleep(backoff * (attempt + 1))
        # busy/exhausted — fall back so a reply still comes. Groq → Gemini (fast
        # cloud) → local Ollama; Gemini → local Ollama.
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

    def _respond_openai(self, system, history, user_text, speaker_verified) -> str:
        messages = ([{"role": "system", "content": system}] + history +
                    [{"role": "user", "content": user_text}])
        tools = _openai_tools()
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
            messages.append({"role": "assistant", "content": msg.content,
                             "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = execute_tool(tc.function.name, args,
                                      speaker_verified=speaker_verified)
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": json.dumps(result, ensure_ascii=False,
                                                       default=str)})
        return (msg.content or "I ran out of tool steps — try asking again.").strip()

    # ---------- Claude ----------

    def _respond_anthropic(self, system, history, user_text, speaker_verified) -> str:
        messages = history + [{"role": "user", "content": user_text}]
        for _ in range(MAX_TOOL_ITERATIONS):
            resp = self.client.messages.create(
                model=self.model, max_tokens=512, system=system,
                tools=TOOL_SCHEMAS, messages=messages)
            if resp.stop_reason != "tool_use":
                break
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input,
                                          speaker_verified=speaker_verified)
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": json.dumps(result, ensure_ascii=False,
                                                          default=str)})
            messages.append({"role": "user", "content": results})
        return "".join(b.text for b in resp.content if b.type == "text").strip()
