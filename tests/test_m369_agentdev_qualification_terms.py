"""M369 — the qualification vocabulary and the authority boundary.

The lexicon is only useful if it is checkable, so every test here asserts a
property of the *data* rather than of the prose that describes it.
"""
from __future__ import annotations

import pytest

from saathi.agentdev.model_qualification import (
    AUTHORITY_BOUNDARY,
    OWNER_DECISION,
    UNIVERSAL_PROHIBITIONS,
    BoundaryViolation,
    Role,
    assert_no_authority_granted,
)
from saathi.agentdev.terminology import (
    BANNED_PHRASES,
    LEXICON,
    Classification,
    audit_surface,
    classify,
    scan_text,
)

M369_TERMS = (
    "model output", "model claim", "verified claim", "unverified claim",
    "contradictory claim", "completion claim", "external evidence",
    "role qualification", "role restriction", "model disqualification",
)


@pytest.mark.parametrize("term", M369_TERMS)
def test_every_required_term_is_pinned(term: str) -> None:
    assert classify(term) is not None, f"{term!r} was never pinned"


@pytest.mark.parametrize("term", M369_TERMS)
def test_every_pinned_term_states_what_it_does_not_mean(term: str) -> None:
    entry = next(t for t in LEXICON if t.term == term)
    assert entry.does_not_mean.strip(), f"{term!r} has no does_not_mean"
    if entry.classification is not Classification.REJECTED:
        assert entry.means.strip(), f"{term!r} has no meaning"


def test_verified_claim_is_deterministic_not_model_evaluated() -> None:
    """The whole point: verification is a deterministic system agreeing."""
    assert classify("verified claim") is Classification.DETERMINISTIC
    assert classify("model claim") is Classification.MODEL_EVALUATED


def test_external_evidence_excludes_another_model() -> None:
    entry = next(t for t in LEXICON if t.term == "external evidence")
    assert "model" in entry.does_not_mean.lower()


def test_role_qualification_does_not_mean_authority() -> None:
    entry = next(t for t in LEXICON if t.term == "role qualification")
    assert "authority" in entry.does_not_mean.lower()


M369_BANNED = (
    "model verified", "the model confirmed", "best model", "model approved",
    "trusted model", "generally capable",
)


@pytest.mark.parametrize("phrase", M369_BANNED)
def test_guard_fires_on_each_new_banned_phrase(phrase: str) -> None:
    findings = scan_text(f"The report says {phrase} for this role.", source="x.md")
    assert [f.phrase for f in findings] == [phrase]


@pytest.mark.parametrize("phrase", M369_BANNED)
def test_each_banned_phrase_names_a_replacement(phrase: str) -> None:
    entry = next(b for b in BANNED_PHRASES if b.phrase == phrase)
    assert entry.reason.strip() and entry.use_instead.strip()


def test_audited_surface_stays_clean() -> None:
    report = audit_surface()
    assert report["clean"], report["findings"][:5]


# ---- the authority boundary -------------------------------------------------


def test_boundary_names_every_forbidden_capability() -> None:
    for required in (
        "shell_access", "filesystem_access", "approval_authority",
        "owner_authority", "deployment_authority", "production_access",
        "live_trading_authority", "crm_write_authority",
        "mission_transition_authority", "provider_credentials", "cloud_access",
    ):
        assert required in AUTHORITY_BOUNDARY


def test_a_role_that_grants_a_boundary_capability_is_refused() -> None:
    with pytest.raises(BoundaryViolation):
        assert_no_authority_granted(["draft research", "shell access for testing"])


def test_every_declared_role_allowance_passes_the_boundary() -> None:
    from saathi.agentdev.model_qualification import ROLE_ALLOWANCES

    for role, allowed in ROLE_ALLOWANCES.items():
        assert_no_authority_granted(list(allowed))  # must not raise
        assert allowed, f"{role} declares no allowance"


def test_universal_prohibitions_cover_the_claim_families() -> None:
    blob = " ".join(UNIVERSAL_PROHIBITIONS).lower()
    for topic in ("modified", "tests", "pushed", "deployment", "approve",
                  "mission state", "tool", "shell"):
        assert topic in blob


def test_owner_decision_records_the_pinned_principles() -> None:
    assert OWNER_DECISION["decision_id"] == "M352_M359_OWNER_ACCEPTED_WITH_LIMITATIONS"
    assert "MODEL_STATEMENTS_DO_NOT_CHANGE_SYSTEM_STATE" in OWNER_DECISION["pinned_principles"]
    assert "COMPLETION_REQUIRES_EXTERNAL_EVIDENCE" in OWNER_DECISION["pinned_principles"]


def test_owner_decision_infers_no_identity() -> None:
    """No name, address or signature field may exist anywhere in the record.

    The ``attribution`` value deliberately *mentions* signatures in order to
    disclaim them, so the check is over the record's keys and over the values
    that are not that disclaimer.
    """
    import json
    import re

    def keys(node, out):
        if isinstance(node, dict):
            for key, value in node.items():
                out.add(key)
                keys(value, out)
        elif isinstance(node, list):
            for item in node:
                keys(item, out)
        return out

    for key in keys(OWNER_DECISION, set()):
        assert key not in ("owner_name", "signature", "signed_by", "signatory")

    without_disclaimer = dict(OWNER_DECISION)
    without_disclaimer.pop("attribution")
    blob = json.dumps(without_disclaimer)
    assert not re.search(r"[\w.+-]+@[\w-]+\.\w+", blob), "an address leaked in"
    for token in ("signature", "signed by", "signatory"):
        assert token not in blob.lower()


def test_qwen3_4b_disposition_is_recorded_verbatim_in_meaning() -> None:
    disposition = OWNER_DECISION["qwen3_4b_disposition"]
    assert disposition["token"] == "QWEN3_4B_RESEARCH_ROLE_NOT_APPROVED_FOR_EXPANSION"
    for prohibition in (
        "NO_UNVERIFIED_COMPLETION_CLAIMS", "NO_TOOL_ACCESS", "NO_FILESYSTEM_ACCESS",
        "NO_SHELL_ACCESS", "NO_CODE_WRITE_ACCESS", "NO_APPROVAL_AUTHORITY",
        "NO_MISSION_TRANSITION_AUTHORITY",
    ):
        assert prohibition in disposition["prohibited"]


def test_no_qualified_role_is_a_role_outcome_not_a_qualification() -> None:
    from saathi.agentdev.model_qualification import ROLE_TIERS

    assert Role.NO_QUALIFIED_ROLE not in ROLE_TIERS


# --------------------------------------------------------------------------
# The terminology audit itself (added during the M369-M376 completion repair)
# --------------------------------------------------------------------------


def test_the_eleven_m369_terms_are_all_pinned() -> None:
    from saathi.agentdev.terminology import M369_TERMS, TERMS_BY_NAME

    assert len(M369_TERMS) == 11
    for term in M369_TERMS:
        assert term in TERMS_BY_NAME, f"{term} is named by M369 but not pinned"


def test_every_pinned_term_states_what_it_does_not_mean() -> None:
    from saathi.agentdev.terminology import M369_TERMS, TERMS_BY_NAME

    for term in M369_TERMS:
        pinned = TERMS_BY_NAME[term]
        assert pinned.means.strip()
        assert pinned.does_not_mean.strip()


def test_the_audit_reports_coverage_per_surface() -> None:
    from saathi.agentdev.terminology import (
        M369_SURFACES,
        M369_TERMS,
        qualification_terminology_audit,
    )

    audit = qualification_terminology_audit()
    assert set(audit["surfaces"]) == set(M369_SURFACES)
    covered = {row["term"] for row in audit["term_coverage"]}
    assert covered == set(M369_TERMS)
    for row in audit["term_coverage"]:
        assert row["declared_surfaces"]
        assert set(row["missing_from"]) <= set(row["declared_surfaces"])


def test_the_audit_records_a_relative_root_not_a_local_path() -> None:
    """Committed evidence has to read the same on any machine."""
    import json as _json

    from saathi.agentdev.terminology import qualification_terminology_audit

    audit = qualification_terminology_audit()
    assert audit["root"] == "."
    assert "/Users/" not in _json.dumps(audit)


def test_the_boundary_tokens_live_in_code_not_only_in_prose() -> None:
    from saathi.agentdev.terminology import (
        M369_BOUNDARY_TOKENS,
        qualification_terminology_audit,
    )

    audit = qualification_terminology_audit()
    found = {row["token"]: row["found_on"] for row in audit["boundary_tokens"]}
    assert set(found) == set(M369_BOUNDARY_TOKENS)
    for token, surfaces in found.items():
        assert "code" in surfaces, f"{token} is documented but not in code"


def test_the_banned_phrase_guard_still_finds_nothing() -> None:
    from saathi.agentdev.terminology import qualification_terminology_audit

    audit = qualification_terminology_audit()
    assert audit["scan"]["clean"], audit["scan"]["findings"]


def test_the_audit_states_what_it_cannot_check() -> None:
    from saathi.agentdev.terminology import qualification_terminology_audit

    limitation = qualification_terminology_audit()["limitation"].lower()
    assert "literal" in limitation
    assert "documentation_only" in limitation
