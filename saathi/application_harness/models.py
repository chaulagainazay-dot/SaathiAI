"""M17.3 canonical application-harness domain model.

A harness is a structured, machine-readable wrapper that lets SaathiOS operate an
application deterministically (preferred over browser/visual control). These are
DEFINITIONS + intents only — no execution here. Design informed by HKUDS/
CLI-Anything (Apache-2.0) harness conventions; no code copied (see
THIRD_PARTY_NOTICES.md). Never store raw secrets in these models.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum


class TrustStatus(str, Enum):
    DISCOVERED = "discovered"
    METADATA_INSPECTED = "metadata_inspected"
    LICENSE_VERIFIED = "license_verified"
    SOURCE_PINNED = "source_pinned"
    DEPENDENCY_SCANNED = "dependency_scanned"
    STATIC_SCANNED = "static_scanned"
    SANDBOX_INSTALLED = "sandbox_installed"
    DETERMINISTIC_TESTED = "deterministic_tested"
    APPLICATION_TESTED = "application_tested"
    SECURITY_REVIEWED = "security_reviewed"
    APPROVED = "approved"
    TRUSTED = "trusted"
    # terminal
    REJECTED = "rejected"
    QUARANTINED = "quarantined"
    DEPRECATED = "deprecated"
    REVOKED = "revoked"
    INCOMPATIBLE = "incompatible"
    COMPROMISED = "compromised"
    EXTERNAL_UNTRUSTED = "external_untrusted"


# only these may execute
EXECUTABLE_TRUST = {TrustStatus.APPROVED, TrustStatus.TRUSTED}


class SideEffect(str, Enum):
    NONE = "none"
    LOCAL_REVERSIBLE = "local_reversible"
    LOCAL_IRREVERSIBLE = "local_irreversible"
    EXTERNAL = "external"


@dataclass
class HarnessOperation:
    operation_id: str
    harness_id: str
    name: str
    description: str = ""
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    risk: int = 0
    approval_requirement: str = "auto"     # auto | approval | manual
    reversibility: str = "reversible"
    side_effect_type: str = SideEffect.NONE.value
    allowed_file_access: str = "workspace"  # none | workspace | roots
    allowed_network_access: str = "none"
    required_application_state: str = "any"
    expected_artifacts: list = field(default_factory=list)
    verification_rules: list = field(default_factory=list)
    timeout: float = 60.0
    retry_policy: str = "transient-only"
    idempotency_behavior: str = "unknown"   # idempotent|conditional|non_idempotent|unknown

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HarnessDefinition:
    harness_id: str
    display_name: str
    application_name: str
    version: str
    schema_version: str = "1"
    application_vendor: str = ""
    description: str = ""
    source_type: str = "local"             # local | cli_anything | source_checkout
    source_repository: str = ""
    source_commit: str = ""                # exact SHA (required for external)
    source_path: str = ""
    license: str = ""
    license_notice: str = ""
    install_method: str = "system_executable"
    entrypoint: str = ""                    # trusted absolute path / constant
    supported_platforms: list = field(default_factory=lambda: ["darwin"])
    supported_application_versions: list = field(default_factory=list)
    required_executables: list = field(default_factory=list)
    required_packages: list = field(default_factory=list)
    required_permissions: list = field(default_factory=list)
    required_file_roots: list = field(default_factory=list)
    required_network_origins: list = field(default_factory=list)
    required_environment_variables: list = field(default_factory=list)
    supported_operations: list = field(default_factory=list)  # operation_ids
    risk_ceiling: int = 2
    verification_strategy: str = "independent"
    sandbox_profile: str = "subprocess_sandbox"
    timeout_policy: float = 120.0
    resource_limits: dict = field(default_factory=dict)
    trust_status: str = TrustStatus.DISCOVERED.value
    validation_status: str = "unverified"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def executable(self) -> bool:
        return TrustStatus(self.trust_status) in EXECUTABLE_TRUST

    def source_fingerprint(self) -> str:
        basis = f"{self.source_repository}|{self.source_commit}|{self.source_path}|{self.version}"
        return hashlib.sha256(basis.encode()).hexdigest()[:24]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HarnessInstallation:
    installation_id: str
    owner_user_id: str
    harness_id: str
    installed_version: str
    source_commit: str = ""
    device_id: str = "local"
    os_user: str = ""
    installation_path: str = ""
    application_path: str = ""
    application_version: str = ""
    environment: str = "pilot"
    enabled: bool = True
    trust_status: str = TrustStatus.DISCOVERED.value
    last_validation: float = 0.0
    last_success: float = 0.0
    last_failure: float = 0.0
    health: str = "unverified"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HarnessActionIntent:
    user_id: str
    session_id: str
    harness_id: str
    operation_id: str
    installation_id: str = ""
    device_id: str = "local"
    normalized_arguments: dict = field(default_factory=dict)
    target_application: str = ""
    target_files: list = field(default_factory=list)
    target_origins: list = field(default_factory=list)
    risk: int = 0
    approval_id: str = ""
    idempotency_key: str = ""
    intent_id: str = ""
    created_at: float = 0.0
    expires_at: float = 0.0

    def __post_init__(self):
        self.intent_id = self.intent_id or "hact_" + uuid.uuid4().hex[:12]
        self.created_at = self.created_at or time.time()
        self.expires_at = self.expires_at or (self.created_at + 600)

    def argument_digest(self) -> str:
        basis = json.dumps({"h": self.harness_id, "op": self.operation_id,
                            "inst": self.installation_id,
                            "args": self.normalized_arguments,
                            "files": sorted(self.target_files),
                            "origins": sorted(self.target_origins)},
                           sort_keys=True, default=str)
        return hashlib.sha256(basis.encode()).hexdigest()[:24]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["argument_digest"] = self.argument_digest()
        return d
