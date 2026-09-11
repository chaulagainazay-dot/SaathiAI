"""FM-I6 output normalization and strict tool-proposal extraction."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import json
import re

from saathi.agent_runtime.harness.local_model_context import contains_secret_shaped, sanitize_text
from saathi.agent_runtime.harness.local_model_types import FORBIDDEN_PROPOSAL_KEYS, PRIVATE_COT_KEYS


_TOOL_BLOCK_RE = re.compile(
    r"<tool_proposal>\s*(\{.*?\})\s*</tool_proposal>",
    re.DOTALL | re.IGNORECASE,
)
_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)

REQUIRED_PROPOSAL_FIELDS = (
    "proposal_id",
    "requested_tool_name",
    "arguments",
    "rationale_summary",
    "confidence",
    "request_correlation_id",
)

# Patterns that stay as ordinary text (never auto-promoted to proposals).
SHELLISH_RE = re.compile(
    r"(?i)(rm\s+-rf|sudo\s+|curl\s+|wget\s+|bash\s+-c|/bin/sh|powershell)",
)
BROWSERISH_RE = re.compile(
    r"(?i)(open\s+browser|navigate\s+to\s+https?://|puppeteer|playwright|selenium)",
)
APPROVAL_CLAIM_RE = re.compile(
    r"(?i)(approval[_\s-]?id\s*[:=]|already\s+approved|approval\s+granted)",
)
TOOLINTENT_CLAIM_RE = re.compile(
    r"(?i)(tool[_\s-]?intent|execution[_\s-]?id\s*[:=]|run[_\s-]?id\s*[:=]\s*[a-f0-9-]{8})",
)
FINANCIAL_RE = re.compile(
    r"(?i)(place\s+order|market\s+order|live\s+trade|withdraw\s+funds|broker\s+api)",
)


@dataclass(frozen=True)
class ExtractedProposal:
    proposal_id: str
    requested_tool_name: str
    arguments: Dict[str, Any]
    rationale_summary: str
    confidence: float
    request_correlation_id: str


@dataclass
class NormalizeResult:
    text: str
    proposals: List[ExtractedProposal]
    warnings: List[str]
    secret_shaped: bool
    scope_forgery: bool
    thinking_stripped: bool
    rejected_proposal_reasons: List[str]


def strip_private_fields(obj: Any) -> Tuple[Any, bool]:
    stripped = False
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in PRIVATE_COT_KEYS or str(k).lower() in PRIVATE_COT_KEYS:
                stripped = True
                continue
            nv, s = strip_private_fields(v)
            stripped = stripped or s
            out[k] = nv
        return out, stripped
    if isinstance(obj, list):
        out_list = []
        for item in obj:
            nv, s = strip_private_fields(item)
            stripped = stripped or s
            out_list.append(nv)
        return out_list, stripped
    return obj, stripped


def _try_parse_proposal(obj: dict, *, correlation_id: str) -> Tuple[Optional[ExtractedProposal], List[str]]:
    reasons: List[str] = []
    if not isinstance(obj, dict):
        return None, ["not_a_dict"]
    # Scope forgery / forbidden keys
    for k in obj.keys():
        if str(k).lower() in FORBIDDEN_PROPOSAL_KEYS or k in FORBIDDEN_PROPOSAL_KEYS:
            return None, [f"forbidden_key:{k}"]
    missing = [f for f in REQUIRED_PROPOSAL_FIELDS if f not in obj]
    if missing:
        return None, [f"missing:{','.join(missing)}"]
    name = obj.get("requested_tool_name")
    if not isinstance(name, str) or not name.strip():
        return None, ["invalid_tool_name"]
    args = obj.get("arguments")
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return None, ["arguments_not_object"]
    # Nested forbidden keys in arguments
    for k in args.keys():
        if str(k).lower() in FORBIDDEN_PROPOSAL_KEYS:
            return None, [f"forbidden_arg_key:{k}"]
    rationale = obj.get("rationale_summary")
    if not isinstance(rationale, str):
        return None, ["invalid_rationale"]
    rationale = sanitize_text(rationale)[:200]
    conf = obj.get("confidence")
    try:
        conf_f = float(conf)
    except (TypeError, ValueError):
        return None, ["invalid_confidence"]
    if conf_f < 0.0 or conf_f > 1.0:
        conf_f = max(0.0, min(1.0, conf_f))
    pid = obj.get("proposal_id")
    if not isinstance(pid, str) or not pid.strip():
        return None, ["invalid_proposal_id"]
    corr = obj.get("request_correlation_id")
    if not isinstance(corr, str):
        return None, ["invalid_correlation"]
    # Correlation must echo request (if provided)
    if correlation_id and corr != correlation_id:
        return None, ["correlation_mismatch"]
    return (
        ExtractedProposal(
            proposal_id=pid.strip(),
            requested_tool_name=name.strip(),
            arguments=dict(args),
            rationale_summary=rationale,
            confidence=conf_f,
            request_correlation_id=corr,
        ),
        reasons,
    )


def extract_tool_proposals(text: str, *, correlation_id: str = "") -> Tuple[List[ExtractedProposal], List[str], str]:
    """Extract strict proposals; return (proposals, reject_reasons, text_without_blocks)."""
    proposals: List[ExtractedProposal] = []
    rejects: List[str] = []
    remaining = text

    def _consume(match: re.Match) -> str:
        nonlocal proposals, rejects
        raw = match.group(1)
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            rejects.append("malformed_json_block")
            return ""  # drop block; do not treat as executable
        prop, reasons = _try_parse_proposal(obj, correlation_id=correlation_id)
        if prop is None:
            rejects.extend(reasons)
            return ""
        proposals.append(prop)
        return ""

    remaining = _TOOL_BLOCK_RE.sub(_consume, remaining)
    # Do NOT auto-parse arbitrary JSON fences as proposals — only tool_proposal tags.
    # Free-form code fences remain text.
    return proposals, rejects, remaining


def normalize_model_text(
    text: str,
    *,
    correlation_id: str = "",
    max_chars: int = 4096,
) -> NormalizeResult:
    raw = sanitize_text(text or "")
    thinking_stripped = False
    # Strip accidental thinking tags
    if re.search(r"(?i)<think>", raw) or re.search(r"(?i)</think>", raw):
        raw = re.sub(r"(?is)<think>.*?</think>", "", raw)
        thinking_stripped = True
    secret = contains_secret_shaped(raw)
    scope_forgery = bool(
        APPROVAL_CLAIM_RE.search(raw)
        or TOOLINTENT_CLAIM_RE.search(raw)
        or re.search(r"(?i)\borganization_id\s*[:=]", raw)
        or re.search(r"(?i)\bworkspace_id\s*[:=]", raw)
    )
    proposals, rejects, remaining = extract_tool_proposals(raw, correlation_id=correlation_id)
    if len(remaining) > max_chars:
        remaining = remaining[:max_chars]
        rejects.append("output_truncated")
    warnings: List[str] = []
    if SHELLISH_RE.search(remaining):
        warnings.append("shell_like_prose_remains_text")
    if BROWSERISH_RE.search(remaining):
        warnings.append("browser_like_prose_remains_text")
    if FINANCIAL_RE.search(remaining):
        warnings.append("financial_like_prose_remains_text")
    if secret:
        warnings.append("secret_shaped_output")
        # Redact secret-looking spans lightly
        remaining = re.sub(
            r"(?i)(api[_-]?key|secret|password|bearer)\s*[:=]\s*\S+",
            r"\1=[REDACTED]",
            remaining,
        )
    if scope_forgery:
        warnings.append("scope_or_approval_claim_in_text")
    return NormalizeResult(
        text=remaining,
        proposals=proposals,
        warnings=warnings,
        secret_shaped=secret,
        scope_forgery=scope_forgery,
        thinking_stripped=thinking_stripped,
        rejected_proposal_reasons=rejects,
    )
