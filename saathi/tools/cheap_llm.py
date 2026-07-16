"""cheap_llm — calls Groq (free) via anthropic-proxy for routine/non-critical tasks."""
from __future__ import annotations
import httpx
from .. import config


def cheap_ask(prompt: str, system: str = "You are a helpful assistant.", max_tokens: int = 1024) -> dict:
    """Cheapest capable model for routine work (captions, summaries, rewrites).

    Routes the SCREENING label with a COST preference through the Model Router
    (SES-002), so the cheapest available provider wins and the chain falls back
    on failure — provider-agnostic, no hardcoded Groq. Fails over to the local
    anthropic-proxy only if the router path errors (belt-and-suspenders).

    M20.3: opt-in governed local inference via ``saathi.inference.compat`` when
    rollout mode is not ``legacy``. Default remains legacy.
    """
    try:
        from saathi.inference.compat import cheap_ask_adopted
        from ..llm import generate
        from ..model_router import ModelLabel, Prefer

        def _legacy(**kwargs):
            return generate(
                kwargs.get("label", ModelLabel.SCREENING),
                kwargs["prompt"],
                system=kwargs.get("system", system),
                prefer=kwargs.get("prefer", Prefer.COST),
                max_tokens=min(int(kwargs.get("max_tokens") or max_tokens), 512),
                timeout=int(kwargs.get("timeout") or 60),
            )

        out = cheap_ask_adopted(
            prompt, system=system, max_tokens=max_tokens, legacy_fn=_legacy,
        )
        # If adoption returned a hard error under governed_local_only, surface it.
        # For legacy failures, keep historical proxy fallback.
        if "error" in out and out.get("path_used") in (
            "governed_local", "governed_local_then_legacy",
        ) and out.get("mode") == "governed_local_only":
            return out
        if "reply" in out:
            return out
        if out.get("mode") and out.get("mode") != "legacy":
            # governed with_fallback already tried legacy; do not double-proxy unless legacy path
            if out.get("path_used") != "legacy":
                return out
    except Exception:
        pass  # fall through to historical paths

    try:
        from ..llm import generate
        from ..model_router import ModelLabel, Prefer
        res = generate(ModelLabel.SCREENING, prompt, system,
                       prefer=Prefer.COST, max_tokens=max_tokens, timeout=60)
        return {"reply": res.text, "model": res.provider, "cost": "cheapest-available",
                "path_used": "legacy", "mode": "legacy"}
    except Exception:
        pass  # fall through to the local proxy below
    try:
        r = httpx.post(
            f"{config.CHEAP_PROXY_URL}/v1/messages",
            headers={"x-api-key": "baadar", "anthropic-version": "2023-06-01"},
            json={
                "model": "claude-haiku-4-5",
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        text = data.get("content", [{}])[0].get("text", "")
        return {"reply": text, "model": "groq/llama-3.3-70b", "cost": "free",
                "path_used": "legacy_proxy", "mode": "legacy"}
    except Exception as e:
        return {"error": str(e)}


def cheap_proxy_status() -> dict:
    """Check if the cheap proxy (anthropic-proxy → Groq) is running."""
    try:
        r = httpx.get(f"{config.CHEAP_PROXY_URL}/healthz", timeout=3)
        return {"status": "running", "url": config.CHEAP_PROXY_URL} if r.text == "ok" else {"status": "error"}
    except Exception as e:
        return {"status": "offline", "error": str(e), "fix": "Run: cd ~/SaathiAI && ./anthropic-proxy .proxy.env"}
