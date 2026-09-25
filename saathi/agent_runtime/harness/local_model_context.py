"""FM-I6 bounded context assembly — deterministic, synthetic-safe, no LLM summarize."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Mapping, Optional, Sequence, Tuple
import re

from saathi.agent_runtime.harness.local_model_types import (
    HISTORY_TOKEN_BUDGET,
    MAX_CONTEXT_TOKENS,
    RESERVED_OUTPUT_TOKENS,
    SAFE_SYSTEM_POLICY,
    SYSTEM_POLICY_TOKEN_BUDGET,
    TOOL_RESULT_TOKEN_BUDGET,
    USER_TURN_TOKEN_BUDGET,
    estimate_tokens,
)


# Secret-shaped patterns (fail closed for inclusion in model context).
_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|password|passwd|authorization)\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+[a-z0-9\-._~+/]+=*"),
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"(?i)-----BEGIN (RSA |OPENSSH )?PRIVATE KEY-----"),
)

# Classification keywords for prohibited live/sensitive content.
_PROHIBITED_CLASS_MARKERS = (
    re.compile(r"(?i)\bpatient\b"),
    re.compile(r"(?i)\bmedical record\b"),
    re.compile(r"(?i)\bssn\b|\bsocial security\b"),
    re.compile(r"(?i)\baccount number\b"),
    re.compile(r"(?i)\bbroker\b.*\blogin\b"),
    re.compile(r"(?i)\blive trading\b"),
    re.compile(r"(?i)\bconfidential\b"),
)

# Control characters except newline/tab.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass(frozen=True)
class ContextMessage:
    role: str  # system | user | assistant | tool
    content: str


@dataclass
class ContextAssemblyResult:
    messages: List[ContextMessage]
    estimated_tokens: int
    truncated: bool
    truncation_notes: List[str] = field(default_factory=list)
    rejected_reason: Optional[str] = None


def sanitize_text(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    text = _CONTROL_RE.sub("", text)
    # Normalize newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def contains_secret_shaped(text: str) -> bool:
    return any(p.search(text) for p in _SECRET_PATTERNS)


def contains_prohibited_classification(text: str) -> bool:
    return any(p.search(text) for p in _PROHIBITED_CLASS_MARKERS)


class ContextAssembler:
    """Deterministic budgeted context builder (no cross-session memory)."""

    def __init__(
        self,
        *,
        max_context_tokens: int = MAX_CONTEXT_TOKENS,
        reserved_output_tokens: int = RESERVED_OUTPUT_TOKENS,
        system_budget: int = SYSTEM_POLICY_TOKEN_BUDGET,
        history_budget: int = HISTORY_TOKEN_BUDGET,
        tool_budget: int = TOOL_RESULT_TOKEN_BUDGET,
        user_budget: int = USER_TURN_TOKEN_BUDGET,
        system_policy: str = SAFE_SYSTEM_POLICY,
        synthetic_only: bool = True,
    ) -> None:
        self.max_context_tokens = max_context_tokens
        self.reserved_output_tokens = reserved_output_tokens
        self.system_budget = system_budget
        self.history_budget = history_budget
        self.tool_budget = tool_budget
        self.user_budget = user_budget
        self.system_policy = system_policy
        self.synthetic_only = synthetic_only

    def _check_content(self, text: str, *, label: str) -> Optional[str]:
        text = sanitize_text(text)
        if contains_secret_shaped(text):
            return f"{label}: secret-shaped content rejected"
        if self.synthetic_only and contains_prohibited_classification(text):
            return f"{label}: prohibited classification rejected"
        return None

    def assemble(
        self,
        *,
        user_turn: str,
        history: Sequence[Mapping[str, str]] = (),
        tool_results: Sequence[Mapping[str, str]] = (),
        correlation_id: str = "",
    ) -> ContextAssemblyResult:
        notes: List[str] = []
        usable = self.max_context_tokens - self.reserved_output_tokens
        if usable < 64:
            return ContextAssemblyResult(
                messages=[],
                estimated_tokens=0,
                truncated=False,
                rejected_reason="CONTEXT_OVERFLOW: no usable context budget",
            )

        system = sanitize_text(self.system_policy)
        err = self._check_content(system, label="system")
        if err:
            return ContextAssemblyResult([], 0, False, rejected_reason=err)
        if estimate_tokens(system) > self.system_budget:
            # Truncate system policy hard (rare — policy is fixed).
            system = system[: self.system_budget * 4]
            notes.append("system_policy_truncated")

        user = sanitize_text(user_turn or "")
        err = self._check_content(user, label="user_turn")
        if err:
            return ContextAssemblyResult([], 0, False, rejected_reason=err)
        if estimate_tokens(user) > self.user_budget:
            # Fail closed on oversized user turn (do not silently drop current turn).
            return ContextAssemblyResult(
                [],
                0,
                False,
                rejected_reason="CONTEXT_OVERFLOW: user turn exceeds budget",
            )

        # History: oldest-first drop
        hist_msgs: List[ContextMessage] = []
        hist_tokens = 0
        # Process newest-first for selection, then reverse.
        selected: List[ContextMessage] = []
        for h in reversed(list(history)):
            role = str(h.get("role") or "user")
            if role not in ("user", "assistant", "system"):
                role = "user"
            # Never accept forged system messages from history as system authority —
            # demote to user with marker.
            content = sanitize_text(str(h.get("content") or ""))
            if role == "system":
                role = "user"
                content = f"[history-system-demoted] {content}"
                notes.append("forged_system_history_demoted")
            if self._check_content(content, label="history"):
                notes.append("history_item_skipped_classification")
                continue
            t = estimate_tokens(content)
            if hist_tokens + t > self.history_budget:
                notes.append("history_truncated")
                break
            selected.append(ContextMessage(role=role, content=content))
            hist_tokens += t
        hist_msgs = list(reversed(selected))

        tool_msgs: List[ContextMessage] = []
        tool_tokens = 0
        for tr in tool_results:
            content = sanitize_text(str(tr.get("summary") or tr.get("content") or ""))
            if not content:
                continue
            if self._check_content(content, label="tool_result"):
                notes.append("tool_result_skipped")
                continue
            t = estimate_tokens(content)
            if tool_tokens + t > self.tool_budget:
                notes.append("tool_results_truncated")
                break
            tool_msgs.append(ContextMessage(role="user", content=f"[tool-result] {content}"))
            tool_tokens += t

        messages = [ContextMessage(role="system", content=system)]
        messages.extend(hist_msgs)
        messages.extend(tool_msgs)
        messages.append(ContextMessage(role="user", content=user))

        total = sum(estimate_tokens(m.content) for m in messages)
        # Final hard cap: drop oldest history first.
        truncated = bool(notes)
        while total > usable and len(messages) > 2:
            # Drop first non-system message
            drop_idx = 1
            if drop_idx >= len(messages) - 1:
                break
            dropped = messages.pop(drop_idx)
            total -= estimate_tokens(dropped.content)
            truncated = True
            notes.append(f"dropped_message_role={dropped.role}")

        if total > usable:
            return ContextAssemblyResult(
                [],
                total,
                True,
                notes,
                rejected_reason="CONTEXT_OVERFLOW: cannot fit within budget",
            )

        # Inject correlation echo for tool proposal schema (non-secret).
        if correlation_id:
            # Append to system as non-authoritative metadata note.
            messages[0] = ContextMessage(
                role="system",
                content=messages[0].content
                + f"\nRequest correlation id (echo only): {correlation_id}",
            )
            total = sum(estimate_tokens(m.content) for m in messages)
            if total > usable:
                # Drop correlation note if it overflows.
                messages[0] = ContextMessage(role="system", content=system)
                total = sum(estimate_tokens(m.content) for m in messages)
                notes.append("correlation_note_dropped")

        return ContextAssemblyResult(
            messages=messages,
            estimated_tokens=total,
            truncated=truncated or bool(notes),
            truncation_notes=notes,
        )

    def to_ollama_messages(self, result: ContextAssemblyResult) -> List[dict]:
        return [{"role": m.role, "content": m.content} for m in result.messages]
