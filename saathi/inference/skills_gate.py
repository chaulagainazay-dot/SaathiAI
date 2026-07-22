"""Third-party / OpenJarvis-compatible skill ingestion gate.

Does not import community skills automatically. High-risk capabilities must
pass ExecutionGateway + approvals. Trading connectors are never directly
invocable by imported skills.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class SkillRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GateDecision(str, Enum):
    ALLOW_QUARANTINE = "allow_quarantine"  # stored but not enabled
    REJECT = "reject"
    ENABLE = "enable"  # only after explicit human enablement path


# Permissions that imported skills must never receive directly
FORBIDDEN_DIRECT_PERMISSIONS = frozenset({
    "production_credentials",
    "payment_systems",
    "live_databases",
    "trading_accounts",
    "deployment_credentials",
    "email_send",
    "destructive_filesystem",
    "unrestricted_shell",
    "trading_connector",
    "place_order",
    "withdraw",
    "disable_kill_switch",
})

# Mount / path patterns denied in sandbox (concept adapted from OJ mount_security)
DEFAULT_BLOCKED_MOUNT_PATTERNS = (
    ".ssh",
    ".gnupg",
    ".env",
    "credentials",
    "id_rsa",
    "id_ed25519",
    ".aws",
    ".config/gcloud",
    ".docker/config.json",
    ".kube/config",
    "trading_guardian",
    "secrets",
)


@dataclass
class SkillManifest:
    source_repository: str
    licence: str
    integrity_hash: str
    version: str
    dependency_manifest: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    required_permissions: list[str] = field(default_factory=list)
    network_access: bool = False
    filesystem_access: list[str] = field(default_factory=list)
    shell_access: bool = False
    secrets_access: bool = False
    risk_classification: SkillRisk = SkillRisk.HIGH
    static_scan_clean: bool = False
    prompt_injection_review: bool = False
    sandbox_test_passed: bool = False
    deterministic_eval_passed: bool = False
    explicitly_enabled: bool = False
    name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_repository": self.source_repository,
            "licence": self.licence,
            "integrity_hash": self.integrity_hash,
            "version": self.version,
            "dependency_manifest": list(self.dependency_manifest),
            "required_tools": list(self.required_tools),
            "required_permissions": list(self.required_permissions),
            "network_access": self.network_access,
            "filesystem_access": list(self.filesystem_access),
            "shell_access": self.shell_access,
            "secrets_access": self.secrets_access,
            "risk_classification": self.risk_classification.value,
            "static_scan_clean": self.static_scan_clean,
            "prompt_injection_review": self.prompt_injection_review,
            "sandbox_test_passed": self.sandbox_test_passed,
            "deterministic_eval_passed": self.deterministic_eval_passed,
            "explicitly_enabled": self.explicitly_enabled,
            "name": self.name,
        }


@dataclass
class GateResult:
    decision: GateDecision
    reasons: list[str] = field(default_factory=list)
    quarantined: bool = False

    @property
    def allowed(self) -> bool:
        return self.decision in {GateDecision.ALLOW_QUARANTINE, GateDecision.ENABLE}


def integrity_hash_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def mount_path_blocked(path: str, patterns: tuple[str, ...] = DEFAULT_BLOCKED_MOUNT_PATTERNS) -> bool:
    low = path.replace("\\", "/").lower()
    for pat in patterns:
        if pat.lower() in low:
            return True
    return False


def skill_requests_trading(manifest: SkillManifest) -> bool:
    tools = {t.lower() for t in manifest.required_tools}
    perms = {p.lower() for p in manifest.required_permissions}
    trading_tokens = {
        "trading_connector", "place_order", "broker", "withdraw",
        "trading_accounts", "leverage", "kill_switch", "trading_guardian",
    }
    if tools & trading_tokens or perms & trading_tokens:
        return True
    return False


def evaluate_skill_manifest(
    manifest: SkillManifest,
    *,
    third_party_enabled: bool = False,
    require_review: bool = True,
    sandbox_required: bool = True,
) -> GateResult:
    reasons: list[str] = []

    if not third_party_enabled:
        return GateResult(GateDecision.REJECT, ["third_party skills disabled by config"])

    if not manifest.source_repository:
        reasons.append("missing source_repository")
    if not manifest.licence or manifest.licence.strip().lower() in {"unknown", "none", "proprietary-unknown"}:
        reasons.append("missing or unknown licence")
    if not manifest.integrity_hash or not re.match(r"^sha256:[0-9a-f]{64}$", manifest.integrity_hash):
        reasons.append("missing or invalid integrity_hash")
    if not manifest.version:
        reasons.append("missing version")

    for perm in manifest.required_permissions:
        if perm in FORBIDDEN_DIRECT_PERMISSIONS:
            reasons.append(f"forbidden permission: {perm}")

    if skill_requests_trading(manifest):
        reasons.append("trading surface requested — must use Trading Guardian via ExecutionGateway only")

    if manifest.secrets_access:
        reasons.append("secrets_access not allowed for third-party skills")

    if manifest.shell_access and manifest.risk_classification in {SkillRisk.HIGH, SkillRisk.CRITICAL}:
        reasons.append("unrestricted or high-risk shell_access blocked")

    for fs in manifest.filesystem_access:
        if mount_path_blocked(fs):
            reasons.append(f"filesystem mount blocked: {fs}")

    if require_review:
        if not manifest.static_scan_clean:
            reasons.append("static scan not clean / not run")
        if not manifest.prompt_injection_review:
            reasons.append("prompt-injection review required")
    if sandbox_required and not manifest.sandbox_test_passed:
        reasons.append("sandbox test required")
    if not manifest.deterministic_eval_passed:
        reasons.append("deterministic evaluation required")

    if reasons:
        # Licence missing → reject; other review failures → reject (fail closed)
        return GateResult(GateDecision.REJECT, reasons)

    if not manifest.explicitly_enabled:
        return GateResult(
            GateDecision.ALLOW_QUARANTINE,
            ["passed gate checks but not explicitly enabled"],
            quarantined=True,
        )
    return GateResult(GateDecision.ENABLE, ["explicitly enabled after full gate"])


def assert_skill_cannot_invoke_trading(manifest: SkillManifest) -> None:
    """Blocking assertion used by regression tests."""
    if skill_requests_trading(manifest):
        raise PermissionError("imported skill cannot directly invoke trading connector")
    for perm in manifest.required_permissions:
        if perm in FORBIDDEN_DIRECT_PERMISSIONS and "trading" in perm:
            raise PermissionError("trading permission forbidden")


# ── Sandbox policy (concept; no Docker requirement for unit tests) ──────────

@dataclass(frozen=True)
class SandboxPolicy:
    read_only_root: bool = True
    mount_allowlist: tuple[str, ...] = ()
    network_enabled: bool = False
    cpu_limit: Optional[float] = 1.0
    memory_limit_mb: Optional[int] = 512
    timeout_seconds: float = 30.0
    output_size_limit_bytes: int = 1_000_000
    privileged: bool = False
    docker_socket: bool = False
    allow_home_secrets: bool = False

    def validate(self) -> list[str]:
        problems = []
        if self.privileged:
            problems.append("privileged containers forbidden")
        if self.docker_socket:
            problems.append("host docker socket forbidden")
        if self.allow_home_secrets:
            problems.append("home secrets access forbidden")
        if self.network_enabled:
            problems.append("network must be disabled by default")
        for m in self.mount_allowlist:
            if mount_path_blocked(m):
                problems.append(f"blocked mount: {m}")
        return problems


def default_sandbox_policy() -> SandboxPolicy:
    return SandboxPolicy(network_enabled=False, privileged=False, docker_socket=False)
