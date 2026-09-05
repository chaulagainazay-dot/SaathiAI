"""M352 — the pinned lexicon and the terminology guard.

Two obligations are tested here. The lexicon must be well formed: one
classification per term, a replacement for every rejection, no unreviewed
classification values. And the guard must actually fire — on every banned
phrase, in every audited file type — while leaving the declared
quote-for-rejection allowances alone.

The final test is the one that matters operationally: the real repository
surface scans clean.
"""
from __future__ import annotations

import json

import pytest

from saathi.agentdev.terminology import (
    AUDITED_SURFACE,
    BANNED_PHRASES,
    LEXICON,
    QUOTED_FOR_REJECTION,
    TERMS_BY_NAME,
    Classification,
    audit_surface,
    classify,
    lexicon_report,
    scan_text,
)


# --------------------------------------------------------------------------
# Lexicon shape
# --------------------------------------------------------------------------


def test_every_reviewed_term_is_pinned_to_one_classification():
    for term in LEXICON:
        assert isinstance(term.classification, Classification)


def test_term_names_are_unique_and_lowercase():
    names = [t.term for t in LEXICON]
    assert len(names) == len(set(names))
    assert names == [n.lower() for n in names]


def test_the_eleven_reviewed_words_are_all_present():
    reviewed = {
        "behaviour coverage",
        "behaviour evaluation",
        "governance evaluation",
        "simulation",
        "certification",
        "enforcement",
        "orchestration",
        "autonomy",
        "runtime",
        "approval",
        "authority",
    }
    assert reviewed <= set(TERMS_BY_NAME)


@pytest.mark.parametrize("term", [t for t in LEXICON if t.classification is Classification.REJECTED])
def test_a_rejected_term_names_its_replacement(term):
    assert term.replacement.strip(), term.term
    assert not term.means.strip(), term.term


@pytest.mark.parametrize("term", [t for t in LEXICON if t.classification is not Classification.REJECTED])
def test_an_accepted_term_states_both_what_it_does_and_does_not_mean(term):
    assert term.means.strip(), term.term
    assert term.does_not_mean.strip(), term.term


def test_behaviour_coverage_is_rejected_and_points_at_the_scenario_suite():
    rejected = TERMS_BY_NAME["behaviour coverage"]
    assert rejected.classification is Classification.REJECTED
    assert rejected.replacement == "behaviour scenario suite"
    assert TERMS_BY_NAME["behaviour scenario suite"].classification is (
        Classification.DETERMINISTIC
    )


def test_behaviour_evaluation_is_reserved_for_a_model_in_the_loop():
    assert TERMS_BY_NAME["behaviour evaluation"].classification is (
        Classification.MODEL_EVALUATED
    )


def test_autonomy_is_rejected_for_this_system():
    assert TERMS_BY_NAME["autonomy"].classification is Classification.REJECTED


def test_certification_is_documentation_only_not_a_technical_control():
    assert TERMS_BY_NAME["certification"].classification is (
        Classification.DOCUMENTATION_ONLY
    )


def test_authority_is_schema_validated_not_a_process_capability():
    term = TERMS_BY_NAME["authority"]
    assert term.classification is Classification.SCHEMA_VALIDATED
    assert "SafetyLevel" in term.means


def test_classify_returns_none_for_an_unreviewed_word():
    assert classify("thoroughput") is None
    assert classify("  Autonomy  ") is Classification.REJECTED


# --------------------------------------------------------------------------
# The guard
# --------------------------------------------------------------------------


@pytest.mark.parametrize("banned", BANNED_PHRASES, ids=lambda b: b.phrase)
def test_every_banned_phrase_is_detected(banned):
    findings = scan_text(f"The system is {banned.phrase} today.", source="x.md")
    assert [f.phrase for f in findings] == [banned.phrase]
    assert findings[0].line == 1
    assert findings[0].use_instead == banned.use_instead


@pytest.mark.parametrize("banned", BANNED_PHRASES, ids=lambda b: b.phrase)
def test_every_banned_phrase_carries_a_reason_and_a_replacement(banned):
    assert banned.reason.strip()
    assert banned.use_instead.strip()


def test_detection_is_case_insensitive():
    assert scan_text("FULLY AUTONOMOUS", source="x.md")


def test_detection_reports_the_line_number_and_excerpt():
    text = "clean line\nanother clean line\nthis is fully autonomous\n"
    findings = scan_text(text, source="docs/x.md")
    assert len(findings) == 1
    assert findings[0].line == 3
    assert findings[0].source == "docs/x.md"
    assert "fully autonomous" in findings[0].excerpt


def test_a_longer_word_containing_a_banned_phrase_is_not_a_finding():
    # "runtime" alone is permitted; only the collided compounds are banned.
    assert not scan_text("The product runtime serves users.", source="x.md")


def test_hyphenated_neighbours_do_not_trigger_a_match():
    assert not scan_text("non-production-ready-ish", source="x.md")


def test_quote_for_rejection_allowances_are_honoured():
    line = "Calling it behaviour coverage is a stretch."
    assert scan_text(line, source="docs/ai-development/overview.md")
    assert not scan_text(line, source="docs/ai-development/limitations.md")


def test_a_file_wide_allowance_suppresses_every_phrase():
    text = "\n".join(b.phrase for b in BANNED_PHRASES)
    assert not scan_text(text, source="saathi/agentdev/terminology.py")
    assert scan_text(text, source="saathi/agentdev/roles.py")


def test_every_allowance_names_a_reason():
    for path_fragment, phrase, reason in QUOTED_FOR_REJECTION:
        assert path_fragment.strip()
        assert phrase.strip()
        assert reason.strip()


# --------------------------------------------------------------------------
# The real surface
# --------------------------------------------------------------------------


def test_the_reviewed_surface_scans_clean():
    report = audit_surface()
    assert report["clean"], json.dumps(report["findings"], indent=2)


def test_the_audit_actually_scanned_the_declared_surface():
    report = audit_surface()
    assert report["files_scanned"] >= len(AUDITED_SURFACE)
    assert report["banned_phrases"] == len(BANNED_PHRASES)
    assert report["lexicon_terms"] == len(LEXICON)


def test_the_audit_publishes_its_own_limitation():
    assert "cannot detect" in audit_surface()["limitation"]


def test_the_audit_writes_nothing(tmp_path):
    before = sorted(p.name for p in tmp_path.iterdir())
    audit_surface()
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_audit_on_an_empty_root_is_clean_and_scans_nothing(tmp_path):
    report = audit_surface(root=tmp_path)
    assert report["clean"]
    assert report["files_scanned"] == 0


def test_audit_finds_a_planted_violation(tmp_path):
    target = tmp_path / "docs" / "ai-development"
    target.mkdir(parents=True)
    (target / "bad.md").write_text("This system is fully autonomous.", encoding="utf-8")
    report = audit_surface(root=tmp_path)
    assert not report["clean"]
    assert report["findings"][0]["phrase"] == "fully autonomous"


# --------------------------------------------------------------------------
# Reporting surface
# --------------------------------------------------------------------------


def test_lexicon_report_is_json_serialisable_and_complete():
    report = lexicon_report()
    json.dumps(report)
    assert len(report["terms"]) == len(LEXICON)
    assert len(report["banned_phrases"]) == len(BANNED_PHRASES)
    assert set(report["classifications"]) == {c.value for c in Classification}


def test_lexicon_report_groups_terms_by_classification():
    grouped = lexicon_report()["by_classification"]
    assert "behaviour coverage" in grouped["rejected"]
    assert "autonomy" in grouped["rejected"]


def test_cli_audit_exits_zero_on_a_clean_surface(capsys):
    from saathi.agentdev.cli import main

    assert main(["terminology", "audit"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["clean"] is True


def test_cli_audit_exits_nonzero_on_a_dirty_surface(tmp_path, capsys):
    from saathi.agentdev.cli import EXIT_FAIL, main

    target = tmp_path / "saathi" / "agentdev"
    target.mkdir(parents=True)
    (target / "x.py").write_text('"""guaranteed safe."""', encoding="utf-8")
    assert main(["terminology", "audit", "--root", str(tmp_path)]) == EXIT_FAIL
    assert json.loads(capsys.readouterr().out)["clean"] is False


def test_cli_classify_reports_an_unreviewed_term_as_not_found(capsys):
    from saathi.agentdev.cli import EXIT_NOT_FOUND, main

    assert main(["terminology", "classify", "throughput"]) == EXIT_NOT_FOUND
    assert json.loads(capsys.readouterr().out)["classification"] is None


def test_cli_lexicon_lists_every_term(capsys):
    from saathi.agentdev.cli import main

    assert main(["terminology", "lexicon"]) == 0
    assert len(json.loads(capsys.readouterr().out)["terms"]) == len(LEXICON)
