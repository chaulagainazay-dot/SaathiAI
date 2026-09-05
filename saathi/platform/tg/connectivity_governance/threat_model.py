"""M318 Provider Connectivity Threat Model."""
from __future__ import annotations

from typing import Any

from saathi.platform.tg.connectivity_governance.models import AUTHORITY_VALUES, RiskLevel

THREATS: list[dict[str, Any]] = [
  {
    "threat_id": "THR-001",
    "category": "identity_and_approval",
    "name": "impersonated_requestor",
    "description": "Attacker impersonates requestor",
    "attack_path": "Adversary attempts impersonated requestor against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-002",
    "category": "identity_and_approval",
    "name": "self_approval",
    "description": "Requestor approves own request",
    "attack_path": "Adversary attempts self approval against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-003",
    "category": "identity_and_approval",
    "name": "forged_approval",
    "description": "Forged approval record",
    "attack_path": "Adversary attempts forged approval against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-004",
    "category": "identity_and_approval",
    "name": "expired_approval_reuse",
    "description": "Reuse of expired approval",
    "attack_path": "Adversary attempts expired approval reuse against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-005",
    "category": "identity_and_approval",
    "name": "approval_scope_expansion",
    "description": "Silent expansion of approved scope",
    "attack_path": "Adversary attempts approval scope expansion against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-006",
    "category": "identity_and_approval",
    "name": "missing_human_acknowledgment",
    "description": "Approval without acknowledgements",
    "attack_path": "Adversary attempts missing human acknowledgment against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-007",
    "category": "identity_and_approval",
    "name": "llm_generated_approval",
    "description": "LLM issues approval",
    "attack_path": "Adversary attempts llm generated approval against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-008",
    "category": "identity_and_approval",
    "name": "replayed_approval",
    "description": "Replay of prior approval",
    "attack_path": "Adversary attempts replayed approval against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-009",
    "category": "credential",
    "name": "credential_pasted_into_chat",
    "description": "Secret pasted into chat",
    "attack_path": "Adversary attempts credential pasted into chat against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-010",
    "category": "credential",
    "name": "credential_logged",
    "description": "Secret written to logs",
    "attack_path": "Adversary attempts credential logged against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-011",
    "category": "credential",
    "name": "credential_committed",
    "description": "Secret committed to git",
    "attack_path": "Adversary attempts credential committed against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-012",
    "category": "credential",
    "name": "credential_stored_in_database",
    "description": "Raw secret in DB",
    "attack_path": "Adversary attempts credential stored in database against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-013",
    "category": "credential",
    "name": "credential_exposed_in_browser",
    "description": "Secret in browser/DOM",
    "attack_path": "Adversary attempts credential exposed in browser against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-014",
    "category": "credential",
    "name": "credential_included_in_evidence",
    "description": "Secret in evidence pack",
    "attack_path": "Adversary attempts credential included in evidence against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-015",
    "category": "credential",
    "name": "credential_reference_substitution",
    "description": "Reference swapped to privileged secret",
    "attack_path": "Adversary attempts credential reference substitution against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-016",
    "category": "credential",
    "name": "credential_reference_reuse",
    "description": "Reuse of disposable reference",
    "attack_path": "Adversary attempts credential reference reuse against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-017",
    "category": "credential",
    "name": "expired_credential_use",
    "description": "Use after expiry",
    "attack_path": "Adversary attempts expired credential use against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-018",
    "category": "credential",
    "name": "privilege_over_scoping",
    "description": "Credential privileges exceed need",
    "attack_path": "Adversary attempts privilege over scoping against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-019",
    "category": "provider",
    "name": "unofficial_endpoint",
    "description": "Call to unofficial host",
    "attack_path": "Adversary attempts unofficial endpoint against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-020",
    "category": "provider",
    "name": "dns_manipulation",
    "description": "DNS points to attacker",
    "attack_path": "Adversary attempts dns manipulation against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-021",
    "category": "provider",
    "name": "provider_impersonation",
    "description": "Fake provider API",
    "attack_path": "Adversary attempts provider impersonation against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-022",
    "category": "provider",
    "name": "sdk_compromise",
    "description": "Compromised SDK",
    "attack_path": "Adversary attempts sdk compromise against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-023",
    "category": "provider",
    "name": "provider_outage",
    "description": "Provider unavailable",
    "attack_path": "Adversary attempts provider outage against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "MODERATE",
    "severity": "MODERATE",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "MODERATE",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-024",
    "category": "provider",
    "name": "rate_limit_failure",
    "description": "Rate limit mishandling",
    "attack_path": "Adversary attempts rate limit failure against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "MODERATE",
    "severity": "MODERATE",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "MODERATE",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-025",
    "category": "provider",
    "name": "undocumented_capability",
    "description": "Using undocumented API",
    "attack_path": "Adversary attempts undocumented capability against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-026",
    "category": "provider",
    "name": "account_environment_mismatch",
    "description": "Wrong env/account",
    "attack_path": "Adversary attempts account environment mismatch against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-027",
    "category": "provider",
    "name": "sandbox_production_confusion",
    "description": "Sandbox vs production mix-up",
    "attack_path": "Adversary attempts sandbox production confusion against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-028",
    "category": "provider",
    "name": "api_version_drift",
    "description": "Unexpected API version",
    "attack_path": "Adversary attempts api version drift against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "MODERATE",
    "severity": "MODERATE",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "MODERATE",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-029",
    "category": "account",
    "name": "wrong_account",
    "description": "Access wrong account",
    "attack_path": "Adversary attempts wrong account against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-030",
    "category": "account",
    "name": "wrong_subaccount",
    "description": "Access wrong subaccount",
    "attack_path": "Adversary attempts wrong subaccount against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-031",
    "category": "account",
    "name": "wrong_environment",
    "description": "Production vs paper confusion",
    "attack_path": "Adversary attempts wrong environment against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-032",
    "category": "account",
    "name": "excessive_account_scope",
    "description": "Unbounded account scope",
    "attack_path": "Adversary attempts excessive account scope against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-033",
    "category": "account",
    "name": "balance_leakage",
    "description": "Balance data exposure",
    "attack_path": "Adversary attempts balance leakage against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-034",
    "category": "account",
    "name": "position_leakage",
    "description": "Position data exposure",
    "attack_path": "Adversary attempts position leakage against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-035",
    "category": "account",
    "name": "private_activity_leakage",
    "description": "Activity leak",
    "attack_path": "Adversary attempts private activity leakage against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-036",
    "category": "account",
    "name": "account_settings_mutation",
    "description": "Unauthorized settings change",
    "attack_path": "Adversary attempts account settings mutation against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-037",
    "category": "execution",
    "name": "hidden_order_submission",
    "description": "Hidden order path",
    "attack_path": "Adversary attempts hidden order submission against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-038",
    "category": "execution",
    "name": "paper_live_environment_confusion",
    "description": "Paper/live mix-up",
    "attack_path": "Adversary attempts paper live environment confusion against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-039",
    "category": "execution",
    "name": "order_modification",
    "description": "Unauthorized modify",
    "attack_path": "Adversary attempts order modification against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-040",
    "category": "execution",
    "name": "order_cancellation",
    "description": "Unauthorized cancel",
    "attack_path": "Adversary attempts order cancellation against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-041",
    "category": "execution",
    "name": "duplicate_orders",
    "description": "Duplicate submission",
    "attack_path": "Adversary attempts duplicate orders against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-042",
    "category": "execution",
    "name": "stale_approval",
    "description": "Order under stale approval",
    "attack_path": "Adversary attempts stale approval against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-043",
    "category": "execution",
    "name": "unbounded_notional",
    "description": "No notional bound",
    "attack_path": "Adversary attempts unbounded notional against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-044",
    "category": "execution",
    "name": "hidden_leverage",
    "description": "Unexpected leverage",
    "attack_path": "Adversary attempts hidden leverage against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-045",
    "category": "execution",
    "name": "short_selling",
    "description": "Unauthorized short",
    "attack_path": "Adversary attempts short selling against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-046",
    "category": "execution",
    "name": "options",
    "description": "Unauthorized options",
    "attack_path": "Adversary attempts options against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-047",
    "category": "execution",
    "name": "transfer",
    "description": "Unauthorized transfer",
    "attack_path": "Adversary attempts transfer against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-048",
    "category": "execution",
    "name": "withdrawal",
    "description": "Unauthorized withdrawal",
    "attack_path": "Adversary attempts withdrawal against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-049",
    "category": "network",
    "name": "unrestricted_outbound_traffic",
    "description": "Open egress",
    "attack_path": "Adversary attempts unrestricted outbound traffic against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-050",
    "category": "network",
    "name": "domain_wildcard",
    "description": "Wildcard domain allow",
    "attack_path": "Adversary attempts domain wildcard against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-051",
    "category": "network",
    "name": "redirect_to_unapproved_host",
    "description": "HTTP redirect attack",
    "attack_path": "Adversary attempts redirect to unapproved host against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-052",
    "category": "network",
    "name": "proxy_bypass",
    "description": "Bypass allowlist via proxy",
    "attack_path": "Adversary attempts proxy bypass against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-053",
    "category": "network",
    "name": "certificate_failure",
    "description": "TLS validation failure",
    "attack_path": "Adversary attempts certificate failure against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-054",
    "category": "network",
    "name": "replay",
    "description": "Request replay",
    "attack_path": "Adversary attempts replay against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-055",
    "category": "network",
    "name": "timeout_ambiguity",
    "description": "Ambiguous timeout",
    "attack_path": "Adversary attempts timeout ambiguity against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "MODERATE",
    "severity": "MODERATE",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "MODERATE",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-056",
    "category": "network",
    "name": "retry_duplication",
    "description": "Retry creates duplicates",
    "attack_path": "Adversary attempts retry duplication against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-057",
    "category": "network",
    "name": "partial_response_handling",
    "description": "Partial response misuse",
    "attack_path": "Adversary attempts partial response handling against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "MODERATE",
    "severity": "MODERATE",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "MODERATE",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-058",
    "category": "network",
    "name": "provider_response_poisoning",
    "description": "Poisoned response",
    "attack_path": "Adversary attempts provider response poisoning against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-059",
    "category": "governance",
    "name": "authority_drift",
    "description": "Authority silently grows",
    "attack_path": "Adversary attempts authority drift against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-060",
    "category": "governance",
    "name": "milestone_authority_inheritance",
    "description": "Higher authority inherited",
    "attack_path": "Adversary attempts milestone authority inheritance against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-061",
    "category": "governance",
    "name": "emergency_shutdown_bypass",
    "description": "Bypass kill switch",
    "attack_path": "Adversary attempts emergency shutdown bypass against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-062",
    "category": "governance",
    "name": "evidence_deletion",
    "description": "Delete evidence",
    "attack_path": "Adversary attempts evidence deletion against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-063",
    "category": "governance",
    "name": "audit_tampering",
    "description": "Tamper with audit",
    "attack_path": "Adversary attempts audit tampering against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-064",
    "category": "governance",
    "name": "policy_override",
    "description": "Silent policy override",
    "attack_path": "Adversary attempts policy override against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-065",
    "category": "governance",
    "name": "human_review_bypass",
    "description": "Skip human review",
    "attack_path": "Adversary attempts human review bypass against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-066",
    "category": "governance",
    "name": "privilege_accumulation",
    "description": "Accumulate privileges",
    "attack_path": "Adversary attempts privilege accumulation against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "MODERATE",
    "impact": "HIGH",
    "severity": "HIGH",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-067",
    "category": "governance",
    "name": "silent_default_allow",
    "description": "Default-allow posture",
    "attack_path": "Adversary attempts silent default allow against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  },
  {
    "threat_id": "THR-068",
    "category": "governance",
    "name": "production_deployment_without_approval",
    "description": "Prod without approval",
    "attack_path": "Adversary attempts production deployment without approval against connectivity governance",
    "affected_assets": [
      "authority",
      "approvals",
      "credentials",
      "providers",
      "evidence"
    ],
    "preconditions": [
      "future connectivity phase or governance bypass attempt"
    ],
    "likelihood": "LOW",
    "impact": "CRITICAL",
    "severity": "CRITICAL",
    "preventive_controls": [
      "no_connectivity_by_default",
      "maker_checker",
      "deny_overrides_allow",
      "raw_credentials_forbidden",
      "domain_allowlists",
      "emergency_shutdown",
      "llm_non_authoritative"
    ],
    "detective_controls": [
      "audit_log",
      "secret_scanners",
      "approval_state_machine",
      "security_scan"
    ],
    "containment": "emergency_shutdown_and_revoke",
    "revocation_action": "revoke_scope_and_approvals",
    "recovery": "human_review_required",
    "evidence": "durable_audit_and_certification",
    "residual_risk": "LOW",
    "residual_note": "Blocked by fail-closed governance; no provider path active",
    "unresolved_critical": False,
    "owner": "connectivity_governance_owner",
    "review_date": "2026-07-30"
  }
]


def list_threats(severity: str | None = None) -> dict[str, Any]:
    items = list(THREATS)
    if severity:
        items = [t for t in items if t["severity"] == severity]
    critical = [t for t in THREATS if t["severity"] == "CRITICAL"]
    high = [t for t in THREATS if t["severity"] == "HIGH"]
    unresolved_critical = [t for t in critical if t.get("unresolved_critical")]
    return {
        "ok": True,
        "count": len(items if not severity else items),
        "total": len(THREATS),
        "threats": items,
        "critical_count": len(critical),
        "high_count": len(high),
        "unresolved_critical": unresolved_critical,
        "unresolved_critical_count": len(unresolved_critical),
        "blocks_canary_eligibility": len(unresolved_critical) > 0,
        "risk_levels": [r.value for r in RiskLevel],
        **AUTHORITY_VALUES,
    }


def risk_summary() -> dict[str, Any]:
    by_cat: dict[str, int] = {}
    by_sev: dict[str, int] = {}
    for t in THREATS:
        by_cat[t["category"]] = by_cat.get(t["category"], 0) + 1
        by_sev[t["severity"]] = by_sev.get(t["severity"], 0) + 1
    unresolved = [t for t in THREATS if t["severity"] == "CRITICAL" and t.get("unresolved_critical")]
    return {
        "ok": True,
        "total_threats": len(THREATS),
        "by_category": by_cat,
        "by_severity": by_sev,
        "critical_blockers": [t["threat_id"] for t in THREATS if t["severity"] == "CRITICAL"],
        "unresolved_critical": [t["threat_id"] for t in unresolved],
        "canary_blocked_by_unresolved_critical": len(unresolved) > 0,
        "preventive_controls_global": [
            "no_connectivity_by_default",
            "human_approval_required",
            "maker_checker",
            "raw_credentials_forbidden",
            "emergency_shutdown_dominates",
            "authority_does_not_implicitly_expand",
            "approval_does_not_equal_activation",
        ],
        "detective_controls_global": [
            "secret_scanners",
            "audit_trail",
            "certification_gates",
            "provider_isolation_scan",
        ],
        "residual_risks": [
            "Future milestones may introduce residual connectivity risk",
            "Human process failures remain possible",
            "Provider documentation drift",
        ],
        **AUTHORITY_VALUES,
    }


def export_threat_model() -> dict[str, Any]:
    return {
        "schema": "M318_PROVIDER_CONNECTIVITY_THREAT_MODEL",
        "threats": list_threats(),
        "risk_summary": risk_summary(),
        **AUTHORITY_VALUES,
    }
