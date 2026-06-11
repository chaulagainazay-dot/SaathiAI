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
        if self.provider == "gemini":
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

    # ---------- public ----------

    def respond(self, user_text: str, session_id: str = "default",
                speaker_verified: bool = False) -> str:
        history = self.memory.recent_turns(session_id, limit=20)
        facts = self.memory.relevant_facts(user_text, limit=8)

        system = SYSTEM_PROMPT
        if facts:
            system += "\n\n# Things you remember about Ajay\n" + "\n".join(f"- {f}" for f in facts)
        system += f"\n\n# Session\nSpeaker verified as Ajay: {speaker_verified}"

        if self.provider in ("gemini", "ollama"):
            reply = self._respond_openai(system, history, user_text, speaker_verified)
        else:
            reply = self._respond_anthropic(system, history, user_text, speaker_verified)

        self.memory.save_turn(session_id, "user", user_text)
        self.memory.save_turn(session_id, "assistant", reply)
        return reply

    # ---------- Gemini (OpenAI-compatible) ----------

    FALLBACK_MODELS = ["gemini-2.5-flash-lite"]

    def _create_with_retry(self, **kwargs):
        """Retry on transient free-tier errors (503 overload, 429 rate limit),
        falling back to alternate Gemini models if the primary stays busy."""
        import time
        from openai import APIStatusError
        if self.provider == "ollama":
            models = [self.model]  # local model — no cloud fallbacks
        else:
            models = [self.model] + [m for m in self.FALLBACK_MODELS if m != self.model]
        last_err = None
        for model in models:
            for attempt in range(4):
                try:
                    return self.client.chat.completions.create(model=model, **kwargs)
                except APIStatusError as e:
                    if e.status_code not in (429, 500, 503):
                        raise
                    last_err = e
                    # "limit: 0" means this model has no free quota at all — skip it
                    if "limit: 0" in str(e):
                        break
                    time.sleep(3 * (attempt + 1))
        raise last_err

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
