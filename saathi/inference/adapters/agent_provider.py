"""Governed agent provider session — owns SDK clients and provider transport (M22).

``saathi.agent.SaathiAgent`` must not construct OpenAI/Anthropic clients or read
API keys. All provider-specific execution for the agent runtime lives here.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class AgentProviderSession:
    """Provider-bound session for agent complete / tool-loop completions."""

    provider: str
    model: str
    client: Any
    is_openai_compat: bool

    def simple_complete(self, system: str, prompt: str, max_tokens: int = 400) -> str:
        """No-tools completion."""
        if self.is_openai_compat:
            resp = self.create_with_retry(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
            )
            return (resp.choices[0].message.content or "").strip()
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    def create_chat(self, **kwargs: Any) -> Any:
        return self.create_with_retry(**kwargs)

    def create_anthropic_message(self, **kwargs: Any) -> Any:
        return self.client.messages.create(model=self.model, **kwargs)

    FALLBACK_MODELS = ["gemini-2.5-flash"]

    def create_with_retry(self, **kwargs: Any) -> Any:
        """Bounded same-provider retries for transient free-tier errors.

        Does **not** perform independent multi-cloud failover (M22: cloud
        fallback remains policy-disabled). Local shimmy/ollama switch is only
        when the configured primary is already local or explicitly configured
        as the session provider — no hidden paid cloud hop.
        """
        from openai import APIStatusError

        if self.provider == "gemini":
            models = [self.model] + [m for m in self.FALLBACK_MODELS if m != self.model]
        else:
            models = [self.model]
        attempts, backoff = (2, 1.0) if self.provider == "groq" else (4, 3.0)
        last_err: Exception | None = None
        for model in models:
            for attempt in range(attempts):
                try:
                    return self.client.chat.completions.create(model=model, **kwargs)
                except APIStatusError as e:
                    transient = e.status_code in (429, 500, 503) or "tool_use_failed" in str(e)
                    if not transient:
                        raise
                    last_err = e
                    if "limit: 0" in str(e) or "PerDay" in str(e):
                        break
                    if attempt < attempts - 1:
                        time.sleep(backoff * (attempt + 1))
                except Exception as e:
                    err_s = str(e).lower()
                    if any(
                        k in err_s
                        for k in (
                            "connect",
                            "network",
                            "name or service",
                            "nodename",
                            "timeout",
                            "unreachable",
                        )
                    ):
                        last_err = e
                        break
                    raise
        # Local-only recovery when primary is cloud and local endpoints exist —
        # does not enable paid cloud fallback chains (groq→gemini removed M22).
        if self.provider in ("gemini", "groq"):
            try:
                self._switch_to_shimmy()
                return self.client.chat.completions.create(model=self.model, **kwargs)
            except Exception:
                pass
            try:
                self._switch_to_ollama()
                return self.client.chat.completions.create(model=self.model, **kwargs)
            except Exception:
                pass
        if last_err is not None:
            raise last_err
        raise RuntimeError("agent_provider_exhausted")

    def _switch_to_shimmy(self) -> None:
        import httpx
        from openai import OpenAI
        from saathi import config

        base = config.SHIMMY_URL.rsplit("/v1", 1)[0]
        httpx.get(f"{base}/v1/models", timeout=3)
        self.client = OpenAI(api_key=config.SHIMMY_API_KEY, base_url=config.SHIMMY_URL)
        self.model = config.SHIMMY_MODEL
        self.provider = "shimmy"
        self.is_openai_compat = True

    def _switch_to_ollama(self) -> None:
        import httpx
        from openai import OpenAI
        from saathi import config

        base = config.OLLAMA_URL.rsplit("/v1", 1)[0]
        httpx.get(base, timeout=3)
        self.client = OpenAI(api_key="ollama", base_url=config.OLLAMA_URL)
        self.model = config.OLLAMA_MODEL
        self.provider = "ollama"
        self.is_openai_compat = True


def _kill_check() -> None:
    try:
        from saathi.inference.provider_policy import is_master_killed

        if is_master_killed():
            raise RuntimeError("SAATHI_INFERENCE_KILL_ALL is active")
    except RuntimeError:
        raise
    except Exception:
        if os.getenv("SAATHI_INFERENCE_KILL_ALL", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            raise RuntimeError("SAATHI_INFERENCE_KILL_ALL is active")


def build_agent_session(provider: Optional[str] = None) -> AgentProviderSession:
    """Construct a provider session. Credentials resolved only here."""
    from saathi import config

    _kill_check()
    prov = (provider or config.LLM_PROVIDER or "").strip().lower()

    if prov == "groq":
        from openai import OpenAI

        key = config.GROQ_API_KEY
        if not key or str(key).startswith("YOUR"):
            raise RuntimeError("MISCONFIGURED: GROQ_API_KEY missing")
        return AgentProviderSession(
            provider="groq",
            model=config.GROQ_MODEL,
            client=OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1"),
            is_openai_compat=True,
        )
    if prov == "gemini":
        from openai import OpenAI

        key = config.GOOGLE_API_KEY
        if not key or str(key).startswith("YOUR"):
            raise RuntimeError("MISCONFIGURED: GOOGLE_API_KEY missing")
        return AgentProviderSession(
            provider="gemini",
            model=config.GEMINI_MODEL,
            client=OpenAI(
                api_key=key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            ),
            is_openai_compat=True,
        )
    if prov == "ollama":
        from openai import OpenAI

        return AgentProviderSession(
            provider="ollama",
            model=config.OLLAMA_MODEL,
            client=OpenAI(api_key="ollama", base_url=config.OLLAMA_URL),
            is_openai_compat=True,
        )
    if prov == "shimmy":
        from openai import OpenAI

        return AgentProviderSession(
            provider="shimmy",
            model=config.SHIMMY_MODEL,
            client=OpenAI(api_key=config.SHIMMY_API_KEY, base_url=config.SHIMMY_URL),
            is_openai_compat=True,
        )
    # Default: Anthropic
    import anthropic

    key = config.ANTHROPIC_API_KEY
    if not key or str(key).startswith("YOUR"):
        raise RuntimeError("MISCONFIGURED: ANTHROPIC_API_KEY missing")
    raw_client = anthropic.Anthropic(api_key=key)
    try:
        from opik.integrations.anthropic import track_anthropic

        client = track_anthropic(raw_client)
    except Exception:
        client = raw_client
    return AgentProviderSession(
        provider="anthropic",
        model=config.CLAUDE_MODEL,
        client=client,
        is_openai_compat=False,
    )
