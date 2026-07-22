"""M23 — Canonical chat context builder.

Owns message ordering, history selection/truncation, system prompt layering,
and privacy-safe metadata. Callers must not build provider-specific message
lists; adapters receive only the bounded canonical list.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Sequence

logger = logging.getLogger(__name__)

# Defaults (configurable via settings keys when present)
DEFAULT_HISTORY_MESSAGE_LIMIT = 12
DEFAULT_HISTORY_FETCH_LIMIT = 20
DEFAULT_PER_MESSAGE_CHARS = 500
DEFAULT_MAX_CONTEXT_CHARS = 28000
DEFAULT_MAX_SYSTEM_CHARS = 8000
CANONICAL_BASE_PROMPT = (
    "You are Saathi, Ajay's AI operating system. Be direct and useful."
)


class SystemPromptLayer(str, Enum):
    CANONICAL_BASE = "canonical_base"
    PRODUCT_POLICY = "product_policy"
    USER_STYLE = "user_style"
    CONVERSATION_OVERRIDE = "conversation_override"
    TOOL_POLICY = "tool_policy"
    AGENT_ROLE = "agent_role"
    MEMORY = "memory"
    KNOWLEDGE = "knowledge"
    PROJECT = "project"
    SUMMARY = "summary"
    TEST_FIXTURE = "test_fixture"
    LEGACY_DUPLICATE = "legacy_duplicate"
    FORBIDDEN = "forbidden"


# Composition order (deterministic)
_LAYER_ORDER = (
    SystemPromptLayer.CANONICAL_BASE,
    SystemPromptLayer.AGENT_ROLE,
    SystemPromptLayer.PRODUCT_POLICY,
    SystemPromptLayer.USER_STYLE,
    SystemPromptLayer.CONVERSATION_OVERRIDE,
    SystemPromptLayer.PROJECT,
    SystemPromptLayer.SUMMARY,
    SystemPromptLayer.MEMORY,
    SystemPromptLayer.KNOWLEDGE,
    SystemPromptLayer.TOOL_POLICY,
)


@dataclass
class ContextBuildResult:
    """Bounded context ready for InferenceRequest / provider adapters."""

    system: str
    prompt: str
    messages: tuple[dict[str, str], ...]
    history_count: int = 0
    truncated: bool = False
    truncation_reason: str = ""
    system_layers_used: tuple[str, ...] = ()
    context_chars: int = 0
    estimate_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def safe_telemetry(self) -> dict[str, Any]:
        return {
            "schema": "m23.chat_context.v1",
            "history_count": self.history_count,
            "truncated": self.truncated,
            "truncation_reason": self.truncation_reason,
            "system_layers_used": list(self.system_layers_used),
            "context_chars": self.context_chars,
            "estimate_tokens": self.estimate_tokens,
            "system_chars": len(self.system or ""),
            "prompt_chars": len(self.prompt or ""),
            "message_count": len(self.messages),
            "system_fingerprint": _fp(self.system),
            "prompt_fingerprint": _fp(self.prompt),
            # never raw content
        }


def _fp(text: str) -> str:
    return "sha256:" + hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:24]


def _estimate_tokens(text: str) -> int:
    # Char/4 heuristic — no new tokenizer dependency in M23
    return max(1, len(text or "") // 4) if text else 0


def _settings_int(name: str, default: int) -> int:
    try:
        from saathi.inference.config import load_inference_settings

        s = load_inference_settings()
        return int(getattr(s, name, default) or default)
    except Exception:
        return default


def classify_system_prompt_source(source: str) -> SystemPromptLayer:
    """Inventory helper — classify a system prompt source label."""
    key = (source or "").strip().lower()
    mapping = {
        "base": SystemPromptLayer.CANONICAL_BASE,
        "canonical": SystemPromptLayer.CANONICAL_BASE,
        "canonical_base": SystemPromptLayer.CANONICAL_BASE,
        "agent": SystemPromptLayer.AGENT_ROLE,
        "agent_role": SystemPromptLayer.AGENT_ROLE,
        "product": SystemPromptLayer.PRODUCT_POLICY,
        "user_style": SystemPromptLayer.USER_STYLE,
        "override": SystemPromptLayer.CONVERSATION_OVERRIDE,
        "conversation_override": SystemPromptLayer.CONVERSATION_OVERRIDE,
        "tool": SystemPromptLayer.TOOL_POLICY,
        "memory": SystemPromptLayer.MEMORY,
        "knowledge": SystemPromptLayer.KNOWLEDGE,
        "project": SystemPromptLayer.PROJECT,
        "summary": SystemPromptLayer.SUMMARY,
        "test": SystemPromptLayer.TEST_FIXTURE,
    }
    return mapping.get(key, SystemPromptLayer.PRODUCT_POLICY)


def compose_system_prompt(
    *,
    base: str = "",
    agent_role: str = "",
    conversation_override: str = "",
    project: str = "",
    summary: str = "",
    memory: str = "",
    knowledge: str = "",
    tool_policy: str = "",
    product_policy: str = "",
    user_style: str = "",
    max_chars: int = DEFAULT_MAX_SYSTEM_CHARS,
) -> tuple[str, tuple[str, ...]]:
    """Deterministic system prompt layering; dedupes identical adjacent blocks."""
    layers: list[tuple[SystemPromptLayer, str]] = []
    base_text = (base or "").strip() or CANONICAL_BASE_PROMPT
    layers.append((SystemPromptLayer.CANONICAL_BASE, base_text))
    if (agent_role or "").strip():
        layers.append((SystemPromptLayer.AGENT_ROLE, agent_role.strip()))
    if (product_policy or "").strip():
        layers.append((SystemPromptLayer.PRODUCT_POLICY, product_policy.strip()))
    if (user_style or "").strip():
        layers.append((SystemPromptLayer.USER_STYLE, user_style.strip()[:500]))
    if (conversation_override or "").strip() and conversation_override.strip() != base_text:
        # Only if distinct from base
        if conversation_override.strip() != CANONICAL_BASE_PROMPT:
            layers.append(
                (SystemPromptLayer.CONVERSATION_OVERRIDE, conversation_override.strip()[:2000])
            )
    if (project or "").strip():
        layers.append((SystemPromptLayer.PROJECT, project.strip()[:1500]))
    if (summary or "").strip():
        layers.append(
            (
                SystemPromptLayer.SUMMARY,
                f"Conversation summary so far: {summary.strip()[:800]}",
            )
        )
    if (memory or "").strip():
        layers.append(
            (
                SystemPromptLayer.MEMORY,
                "Relevant memory (scope-checked; cite [mem:…] you use):\n"
                + memory.strip()[:3000],
            )
        )
    if (knowledge or "").strip():
        layers.append(
            (
                SystemPromptLayer.KNOWLEDGE,
                "Relevant knowledge (cite [chunk refs] you use):\n"
                + knowledge.strip()[:3000],
            )
        )
    if (tool_policy or "").strip():
        layers.append((SystemPromptLayer.TOOL_POLICY, tool_policy.strip()[:1000]))

    # Sort by canonical order, preserve only known layers
    order_idx = {layer: i for i, layer in enumerate(_LAYER_ORDER)}
    layers.sort(key=lambda x: order_idx.get(x[0], 99))

    parts: list[str] = []
    used: list[str] = []
    seen_content: set[str] = set()
    for layer, text in layers:
        norm = text.strip()
        if not norm or norm in seen_content:
            continue
        seen_content.add(norm)
        parts.append(norm)
        used.append(layer.value)

    composed = "\n\n".join(parts)
    if len(composed) > max_chars:
        composed = composed[: max_chars - 20] + "\n…[truncated]"
    return composed, tuple(used)


def select_history(
    messages: Sequence[dict[str, Any]],
    *,
    limit: int = DEFAULT_HISTORY_MESSAGE_LIMIT,
    per_message_chars: int = DEFAULT_PER_MESSAGE_CHARS,
    exclude_last_user: bool = True,
    conversation_id: str = "",
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Deterministic bounded history; preserves tool-call pairs when present.

    ``messages`` are store rows (role, content, …) already scoped to one conversation.
    """
    meta: dict[str, Any] = {
        "input_count": len(messages),
        "truncated": False,
        "truncation_reason": "",
        "conversation_id": conversation_id or "",
    }
    rows = list(messages or [])
    # Only valid roles
    allowed = {"user", "assistant", "system", "tool"}
    cleaned: list[dict[str, str]] = []
    for m in rows:
        role = str(m.get("role") or "").strip().lower()
        if role not in allowed:
            continue
        content = str(m.get("content") or "")
        if not content.strip():
            continue
        # Cross-conversation guard
        mid_cid = str(m.get("conversation_id") or "")
        if conversation_id and mid_cid and mid_cid != conversation_id:
            meta["cross_conversation_denied"] = True
            continue
        cleaned.append(
            {
                "role": role,
                "content": content[:per_message_chars],
                "id": str(m.get("id") or ""),
            }
        )

    # Drop trailing user if it is the just-added current turn (caller re-adds)
    work = cleaned[:-1] if exclude_last_user and cleaned else cleaned

    # Preserve tool pairs: if truncating, do not leave orphan tool without assistant
    if len(work) > limit:
        meta["truncated"] = True
        meta["truncation_reason"] = "message_count_limit"
        work = work[-limit:]
        # If first remaining is tool, drop until non-tool
        while work and work[0]["role"] == "tool":
            work = work[1:]

    # Drop system from history — system is owned by compose_system_prompt
    work = [m for m in work if m["role"] != "system"]

    out = [{"role": m["role"], "content": m["content"]} for m in work]
    meta["selected_count"] = len(out)
    return out, meta


def build_prompt_from_history(
    history: Sequence[dict[str, str]],
    current_user_message: str,
    *,
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
) -> tuple[str, bool, str]:
    """Build flat prompt string compatible with existing ChatLLMAdapter.

    Returns (prompt, truncated, reason).
    """
    lines: list[str] = []
    for m in history:
        role = m.get("role") or "user"
        content = m.get("content") or ""
        lines.append(f"{role}: {content}")
    body = "\n".join(lines)
    user = (current_user_message or "").strip()
    if body:
        prompt = body + "\nuser: " + user
    else:
        prompt = user

    truncated = False
    reason = ""
    if len(prompt) > max_context_chars:
        truncated = True
        reason = "context_char_limit"
        # Keep tail including current user message
        keep = max_context_chars - len(user) - 20
        if keep < 100:
            prompt = user[:max_context_chars]
        else:
            prompt = "…[truncated]\n" + body[-(keep):] + "\nuser: " + user
    return prompt, truncated, reason


def build_chat_context(
    *,
    conversation_id: str,
    user_message: str,
    history_messages: Sequence[dict[str, Any]] | None = None,
    agent_role: str = "",
    system_override: str = "",
    project_context: str = "",
    summary: str = "",
    memory_context: str = "",
    knowledge_context: str = "",
    tool_policy: str = "",
    history_limit: Optional[int] = None,
    per_message_chars: int = DEFAULT_PER_MESSAGE_CHARS,
    max_context_chars: Optional[int] = None,
    max_system_chars: int = DEFAULT_MAX_SYSTEM_CHARS,
) -> ContextBuildResult:
    """Single authority for chat context construction."""
    hist_limit = history_limit if history_limit is not None else DEFAULT_HISTORY_MESSAGE_LIMIT
    max_ctx = max_context_chars if max_context_chars is not None else DEFAULT_MAX_CONTEXT_CHARS

    base = CANONICAL_BASE_PROMPT
    override = (system_override or "").strip()
    # If override is a full custom system (agent path passes empty and uses agent_role),
    # treat non-empty override as conversation_override only when distinct
    system, layers = compose_system_prompt(
        base=base if not (override and not agent_role) else (override or base),
        agent_role=agent_role,
        conversation_override="" if agent_role else "",
        project=project_context,
        summary=summary,
        memory=memory_context,
        knowledge=knowledge_context,
        tool_policy=tool_policy,
        max_chars=max_system_chars,
    )
    # When caller passes system_override without agent, layer it carefully
    if override and not agent_role and override not in (base, CANONICAL_BASE_PROMPT):
        system, layers = compose_system_prompt(
            base=base,
            conversation_override=override,
            project=project_context,
            summary=summary,
            memory=memory_context,
            knowledge=knowledge_context,
            tool_policy=tool_policy,
            max_chars=max_system_chars,
        )

    hist, hist_meta = select_history(
        history_messages or [],
        limit=hist_limit,
        per_message_chars=per_message_chars,
        exclude_last_user=True,
        conversation_id=conversation_id,
    )
    prompt, trunc2, reason2 = build_prompt_from_history(
        hist, user_message, max_context_chars=max_ctx
    )
    truncated = bool(hist_meta.get("truncated") or trunc2)
    reason = str(hist_meta.get("truncation_reason") or reason2 or "")

    # Canonical messages list for adapters
    msgs: list[dict[str, str]] = [{"role": "system", "content": system}]
    msgs.extend(hist)
    msgs.append({"role": "user", "content": (user_message or "")[:per_message_chars * 4]})

    context_chars = len(system) + len(prompt)
    est = _estimate_tokens(system) + _estimate_tokens(prompt)

    return ContextBuildResult(
        system=system,
        prompt=prompt,
        messages=tuple(msgs),
        history_count=len(hist),
        truncated=truncated,
        truncation_reason=reason,
        system_layers_used=layers,
        context_chars=context_chars,
        estimate_tokens=est,
        metadata={
            "conversation_id": conversation_id,
            "history_meta": {
                k: v
                for k, v in hist_meta.items()
                if k not in ("content", "messages", "raw")
            },
        },
    )


# Module-level singleton authority marker for inventory tests
CONTEXT_BUILDER_AUTHORITY = "saathi.chat.context.build_chat_context"
