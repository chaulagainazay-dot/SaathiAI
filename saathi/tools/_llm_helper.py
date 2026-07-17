"""Shared LLM helper for studio tools — M21.3 compatibility facade.

Routes exclusively through ``saathi.llm.generate`` (ModelRouter) after
preflight. Direct provider HTTP chains removed (were DIRECT_PROVIDER_BYPASS).

Public API preserved: ``ask_llm(prompt, system, timeout, max_tokens) -> str``.
"""
from __future__ import annotations

import json
import re
from typing import Any

CALLER_ID = "tools_llm_helper"
PATH_ID = "tools_llm_helper"


def ask_llm(
    prompt: str,
    system: str = "You are a helpful assistant. Reply ONLY with valid JSON.",
    timeout: int = 60,
    max_tokens: int = 4000,
) -> str:
    """Call an LLM via Model Router under registered caller ``tools_llm_helper``.

    No direct provider SDK or URL calls. No nested retry beyond ModelRouter chain.
    """
    from saathi.inference.legacy_facade import preflight_inference
    from saathi.llm import generate
    from saathi.model_router import ModelLabel, Prefer

    # Cap historical high defaults to caller policy (preflight enforces)
    pf = preflight_inference(
        caller_id=CALLER_ID,
        path_id=PATH_ID,
        prompt=prompt or "",
        system=system or "",
        max_tokens=int(max_tokens),
        timeout=float(timeout),
    )
    if not pf.ok:
        raise RuntimeError(pf.error_message or pf.reason_code or "ask_llm_preflight_denied")

    res = generate(
        ModelLabel.STANDARD,
        prompt,
        system,
        prefer=Prefer.QUALITY,
        max_tokens=int(pf.max_output_tokens),
        timeout=int(max(1, min(pf.timeout_seconds, 300))),
        caller_id=CALLER_ID,
        skip_preflight=True,  # already preflighted
    )
    return res.text


def extract_json(text: str) -> dict:
    """Extract first JSON object from LLM reply, with multi-pass cleaning."""
    # Strip markdown fences
    text = re.sub(r"```(?:json)?", "", text).strip()

    # Find outermost { ... }
    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON found in: {text[:200]}")

    # Walk to find matching closing brace
    depth, end = 0, -1
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    raw = text[start:end] if end != -1 else text[start:]

    # First attempt — direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Second attempt — strip control characters (tabs, newlines inside strings)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Third attempt — remove trailing comma before } or ]
    fixed = re.sub(r",\s*([\}\]])", r"\1", cleaned)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON parse failed after 3 attempts: {e} | text[:300]={raw[:300]}")
