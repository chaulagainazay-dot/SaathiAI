"""Runtime Governance Engine (Safety Harness) — deterministic action governance.

Every action flows through here BEFORE anything executes. Nothing bypasses it —
shell, browser, Git, finance, deployment, Telegram, all of it:

    Agent → Governance Engine → Model Router → Tool Registry → Execution

More than a permission checker — a layered governance pipeline. Layers BUILT:
    L1  Action Classification (L0–L5, deterministic, never an LLM)
    L2  Capability Validation (allowed models / tools / max safety / approval)
    L3  Identity Validation   (guest / user / admin / automation / scheduled job)
    L5  Resource Guardrails    (injected — wired to Storage Intelligence, budget)
    L6  Approval Workflow      (profile-driven: auto / human / dual)
    L7  Audit Logging          (who/what/why/when/capability/risk/result)
    L9  Risk Scoring           (deterministic 0–1 + confidence)
    +   Safety Profiles        (development / production / emergency / offline …)

Layers DEFERRED to their milestones (Development Rule #1 — don't build ahead):
    L4  Context Validation     (partly covered by resource guardrails today)
    L8  Compliance modules     (GDPR/HIPAA/SOC2 — per-product, future)
    L10 Learning from denials  (M2 — needs the Memory Promotion Engine)

Classification is **rule-based and deterministic** — never an LLM. An LLM may
assist reasoning AFTER classification; the level itself comes from rules so it
is predictable and auditable (AP-14: autonomy earned, matched by governance).

Testable in isolation (AP-12): pure functions + injected policies / resource
checks / audit sink; no network.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import IntEnum, Enum
from typing import Callable


class SafetyLevel(IntEnum):
    L0 = 0   # read-only
    L1 = 1   # low-risk automation
    L2 = 2   # local modification
    L3 = 3   # external side effects
    L4 = 4   # financial / production / deployment
    L5 = 5   # destructive / irreversible


class Approval(str, Enum):
    AUTOMATIC = "automatic"     # no human needed
    HUMAN = "human"             # human must approve
    CODE_CONFIRM = "code_confirm"  # human + explicit confirmation code (L5)


class Identity(str, Enum):
    GUEST = "guest"
    USER = "user"
    ADMIN = "admin"
    AUTOMATION = "automation"
    SCHEDULED_JOB = "scheduled_job"


class SafetyProfile(str, Enum):
    DEVELOPMENT = "development"   # lenient — fast iteration
    TESTING = "testing"
    PRODUCTION = "production"     # stricter — external actions need approval
    EMERGENCY = "emergency"       # most restrictive
    TRAVEL = "travel"            # like production (operator away)
    OFFLINE = "offline"          # deny external side effects entirely


# Approval matrix per profile: level → required approval.
_PROFILE_APPROVAL: dict[SafetyProfile, dict[SafetyLevel, Approval]] = {
    SafetyProfile.DEVELOPMENT: {
        SafetyLevel.L0: Approval.AUTOMATIC, SafetyLevel.L1: Approval.AUTOMATIC,
        SafetyLevel.L2: Approval.AUTOMATIC, SafetyLevel.L3: Approval.AUTOMATIC,
        SafetyLevel.L4: Approval.HUMAN, SafetyLevel.L5: Approval.CODE_CONFIRM,
    },
    SafetyProfile.PRODUCTION: {
        SafetyLevel.L0: Approval.AUTOMATIC, SafetyLevel.L1: Approval.AUTOMATIC,
        SafetyLevel.L2: Approval.AUTOMATIC, SafetyLevel.L3: Approval.HUMAN,
        SafetyLevel.L4: Approval.HUMAN, SafetyLevel.L5: Approval.CODE_CONFIRM,
    },
    SafetyProfile.EMERGENCY: {
        SafetyLevel.L0: Approval.AUTOMATIC, SafetyLevel.L1: Approval.AUTOMATIC,
        SafetyLevel.L2: Approval.HUMAN, SafetyLevel.L3: Approval.HUMAN,
        SafetyLevel.L4: Approval.CODE_CONFIRM, SafetyLevel.L5: Approval.CODE_CONFIRM,
    },
}
_PROFILE_APPROVAL[SafetyProfile.TESTING] = _PROFILE_APPROVAL[SafetyProfile.DEVELOPMENT]
_PROFILE_APPROVAL[SafetyProfile.TRAVEL] = _PROFILE_APPROVAL[SafetyProfile.PRODUCTION]
_PROFILE_APPROVAL[SafetyProfile.OFFLINE] = _PROFILE_APPROVAL[SafetyProfile.PRODUCTION]


def approval_for(level: SafetyLevel, profile: SafetyProfile) -> Approval:
    return _PROFILE_APPROVAL[profile][level]


def risk_score(level: SafetyLevel, matched: bool) -> tuple[float, float]:
    """Deterministic risk (0–1) and confidence (0–1).
    Risk scales with level; confidence is high when a rule matched, lower when
    we fell back to the conservative default."""
    return round(level.value / 5.0, 3), (0.97 if matched else 0.6)


# ── Deterministic classification rules ───────────────────────────────────
# Keyword → level. Tokens are matched exactly (after splitting on non-alnum),
# so "read_file" → {read, file} matches "read". Most restrictive always wins.
_KEYWORDS: list[tuple[SafetyLevel, set[str]]] = [
    (SafetyLevel.L5, {"delete", "destroy", "drop", "wipe", "format", "purge",
                      "terminate", "erase", "truncate", "rmrf"}),
    (SafetyLevel.L4, {"deploy", "production", "payment", "transfer", "trade", "buy",
                      "sell", "withdraw", "money", "invoice", "refund", "charge", "finance"}),
    (SafetyLevel.L3, {"send", "post", "publish", "email", "telegram", "tweet",
                      "push", "upload", "share", "reply", "comment"}),
    (SafetyLevel.L2, {"write", "edit", "save", "create", "update", "commit",
                      "modify", "rename", "move", "store"}),
    (SafetyLevel.L1, {"schedule", "summarize", "classify", "generate", "draft", "plan"}),
    (SafetyLevel.L0, {"read", "get", "list", "status", "view", "search",
                      "fetch", "show", "inspect", "check", "analyze"}),
]

_UNKNOWN_DEFAULT = SafetyLevel.L2   # conservative — an unrecognized action is never free


def _classify_raw(tool: str, args: dict | None = None) -> SafetyLevel | None:
    """Deterministic. Returns the most restrictive matched level, or None if
    no keyword matched at all (lets a capability policy govern instead)."""
    text = tool.lower()
    if args:
        text += " " + " ".join(str(k).lower() for k in args.keys())
    tokens = set(re.split(r"[^a-z0-9]+", text))
    matched = [lvl for lvl, kws in _KEYWORDS if tokens & kws]
    return max(matched) if matched else None


def classify(tool: str, args: dict | None = None) -> SafetyLevel:
    """Public classifier: matched level, or the conservative default if unknown."""
    raw = _classify_raw(tool, args)
    return raw if raw is not None else _UNKNOWN_DEFAULT


def default_approval(level: SafetyLevel) -> Approval:
    if level >= SafetyLevel.L5:
        return Approval.CODE_CONFIRM
    if level >= SafetyLevel.L4:
        return Approval.HUMAN
    return Approval.AUTOMATIC


def audit_required(level: SafetyLevel) -> bool:
    return level >= SafetyLevel.L3


# ── Capability-aware policy ──────────────────────────────────────────────
@dataclass
class CapabilityPolicy:
    name: str
    safety_level: SafetyLevel
    approval: Approval
    allowed_models: frozenset[str] = field(default_factory=frozenset)      # empty = any
    allowed_tools: frozenset[str] = field(default_factory=frozenset)       # empty = any
    allowed_identities: frozenset[Identity] = field(default_factory=frozenset)  # empty = any
    audit: bool = False


@dataclass
class ActionRequest:
    tool: str
    args: dict = field(default_factory=dict)
    capability: str | None = None
    model: str | None = None
    identity: Identity = Identity.USER
    why: str = ""                       # for the audit trail


@dataclass
class SafetyDecision:
    level: SafetyLevel
    approval: Approval
    allowed: bool
    audit: bool
    reasons: list[str] = field(default_factory=list)
    # governance-engine additions:
    risk: float = 0.0
    confidence: float = 1.0
    identity_ok: bool = True
    resource_ok: bool = True
    profile: SafetyProfile = SafetyProfile.DEVELOPMENT


def _noop_resource(_action: "ActionRequest") -> tuple[bool, str]:
    return True, ""


def _noop_audit(_record: dict) -> None:
    pass


class SafetyHarness:
    """The Runtime Governance Engine. Runs the layered pipeline, then gates."""

    def __init__(
        self,
        policies: dict[str, CapabilityPolicy] | None = None,
        profile: SafetyProfile = SafetyProfile.DEVELOPMENT,
        resource_check: Callable[["ActionRequest"], tuple[bool, str]] = _noop_resource,
        audit_sink: Callable[[dict], None] = _noop_audit,
    ):
        self.policies = policies or {}
        self.profile = profile
        self._resource_check = resource_check      # L5 — wired to Storage Intelligence / budget
        self._audit = audit_sink                   # L7

    def register_policy(self, policy: CapabilityPolicy) -> None:
        self.policies[policy.name] = policy

    def evaluate(self, action: ActionRequest) -> SafetyDecision:
        reasons: list[str] = []
        raw = _classify_raw(action.tool, action.args)
        matched = raw is not None
        policy = self.policies.get(action.capability) if action.capability else None
        allowed = True
        identity_ok = True
        resource_ok = True

        # L1 + L2 — classification and capability level
        if policy:
            level = policy.safety_level
            if raw is not None and raw > level:
                reasons.append(f"tool classified {raw.name} — escalated above policy {policy.safety_level.name}")
                level = raw
            else:
                reasons.append(f"policy {policy.name!r} sets level {level.name}")
            if policy.allowed_tools and action.tool not in policy.allowed_tools:
                allowed = False
                reasons.append(f"tool {action.tool!r} not permitted for capability {policy.name!r}")
            if policy.allowed_models and action.model and action.model not in policy.allowed_models:
                allowed = False
                reasons.append(f"model {action.model!r} not permitted for capability {policy.name!r}")
            # L3 — identity
            if policy.allowed_identities and action.identity not in policy.allowed_identities:
                allowed = identity_ok = False
                reasons.append(f"identity {action.identity.value!r} not permitted for capability {policy.name!r}")
        else:
            level = raw if raw is not None else _UNKNOWN_DEFAULT
            reasons.append(f"classified {level.name} from tool={action.tool!r}")
            if action.capability:
                reasons.append(f"no policy registered for capability {action.capability!r}")

        # L6 — approval from the active profile, escalated by any policy requirement
        approval = approval_for(level, self.profile)
        if policy:
            approval = _stricter_approval(approval, policy.approval)

        # OFFLINE profile denies external side effects outright
        if self.profile is SafetyProfile.OFFLINE and level >= SafetyLevel.L3:
            allowed = False
            reasons.append("OFFLINE profile: external side effects (L3+) denied")

        # L5 — resource guardrails (injected; e.g. Storage Intelligence)
        resource_ok, rreason = self._resource_check(action)
        if not resource_ok:
            allowed = False
            reasons.append(f"resource guardrail: {rreason}")

        # L7 audit flag + L9 risk score
        audit = (policy.audit if policy else False) or audit_required(level)
        risk, confidence = risk_score(level, matched)

        return SafetyDecision(
            level=level, approval=approval, allowed=allowed, audit=audit, reasons=reasons,
            risk=risk, confidence=confidence, identity_ok=identity_ok,
            resource_ok=resource_ok, profile=self.profile,
        )

    def gate(self, action: ActionRequest, *, human_approved: bool = False,
             code_confirmed: bool = False) -> SafetyDecision:
        """Full gate: evaluate, enforce approvals, then always audit (L7)."""
        decision = self.evaluate(action)
        if decision.allowed:
            if decision.approval is Approval.HUMAN and not human_approved:
                decision.allowed = False
                decision.reasons.append("requires human approval — not provided")
            elif decision.approval is Approval.CODE_CONFIRM and not code_confirmed:
                decision.allowed = False
                decision.reasons.append("requires code confirmation — not provided")
        self._emit_audit(action, decision)
        return decision

    def _emit_audit(self, action: ActionRequest, d: SafetyDecision) -> None:
        # L7 — never optional for anything that ran the gate.
        self._audit({
            "who": action.identity.value,
            "what": action.tool,
            "why": action.why,
            "when": time.time(),
            "capability": action.capability,
            "level": d.level.name,
            "risk": d.risk,
            "approval": d.approval.value,
            "result": "allowed" if d.allowed else "denied",
            "model": action.model,
            "reasons": d.reasons,
        })


def _stricter_approval(a: Approval, b: Approval) -> Approval:
    order = {Approval.AUTOMATIC: 0, Approval.HUMAN: 1, Approval.CODE_CONFIRM: 2}
    return a if order[a] >= order[b] else b


def storage_resource_check(predictive, plan_for: Callable[["ActionRequest"], object]):
    """L5 resource guardrail wired to the Predictive Storage Engine.

    ``plan_for(action)`` returns a RenderPlan for render actions, or None for
    anything that isn't a render (which is then allowed through this check).
    A render that can't finish on available disk is denied here — governance
    and Storage Intelligence meeting exactly where they should.
    """
    def check(action: "ActionRequest") -> tuple[bool, str]:
        plan = plan_for(action)
        if plan is None:
            return True, ""
        decision = predictive.decide(plan)
        if decision.safe:
            return True, ""
        need = decision.estimate.peak_bytes / 1e9
        have = decision.free_bytes / 1e9
        return False, f"render needs {need:.0f}GB, only {have:.0f}GB free"
    return check


# A couple of seed policies (the examples from the spec).
def default_policies() -> dict[str, CapabilityPolicy]:
    return {p.name: p for p in [
        CapabilityPolicy(
            "GitHub Deployment", SafetyLevel.L4, Approval.HUMAN,
            allowed_models=frozenset({"openai/gpt-4o", "claude/sonnet"}),
            allowed_tools=frozenset({"deploy_production"}),
            audit=True,
        ),
        CapabilityPolicy(
            "AI Studio Storyboard", SafetyLevel.L1, Approval.AUTOMATIC,
            allowed_models=frozenset({"ollama/local", "gemini/2.5-flash-lite"}),
            allowed_tools=frozenset({"storyboard_engine"}),
        ),
    ]}
