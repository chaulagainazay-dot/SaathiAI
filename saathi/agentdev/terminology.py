"""M352 — Pinned terminology for the development-agent environment.

The M344–M351 simulated mission ended with one question referred upward: may a
ten-scenario suite be called *behaviour coverage*? This module is the owner's
answer, expressed as data rather than prose, so that the answer is checkable.

Two things live here.

**The lexicon.** Every ambiguous term the owner reviewed, each pinned to exactly
one :class:`Classification`, with the claim it is now allowed to carry and the
claim it is not. A term the owner rejected outright carries
:data:`Classification.REJECTED` and names its replacement.

**The guard.** :func:`scan_text` looks for a small, closed set of banned
phrases — literal strings, matched case-insensitively. It is a *lexical* guard
and nothing more: it catches the specific overstatements the owner named, and it
cannot detect an overstatement phrased in words nobody listed. That limitation
is the point of stating it here rather than claiming the surface is
"terminology enforced".

Classification vocabulary, fixed:

``technically_enforced``
    A code path raises or exits non-zero. Removing the control breaks a test.
``schema_validated``
    Malformed input is refused at construction or load.
``deterministic``
    Same input, same output, no model and no network involved.
``model_evaluated``
    A local model produced the behaviour and a rubric scored it. Establishes a
    measurement of one model at one moment, never a property of models.
``advisory_only``
    Guidance an agent may ignore. Detectable after the fact, not preventable.
``documentation_only``
    A statement about the system written by a human. Carries no runtime effect.
``rejected``
    The owner removed this wording. It has a named replacement.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from saathi.config import ROOT


class Classification(str, Enum):
    TECHNICALLY_ENFORCED = "technically_enforced"
    SCHEMA_VALIDATED = "schema_validated"
    DETERMINISTIC = "deterministic"
    MODEL_EVALUATED = "model_evaluated"
    ADVISORY_ONLY = "advisory_only"
    DOCUMENTATION_ONLY = "documentation_only"
    REJECTED = "rejected"


@dataclass(frozen=True)
class PinnedTerm:
    """One reviewed term and the exact claim it is now allowed to carry."""

    term: str
    classification: Classification
    means: str
    does_not_mean: str
    replacement: str = ""
    surfaces: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["classification"] = self.classification.value
        return d


#: The eleven terms the owner reviewed, in the order they were reviewed.
#:
#: Where one word carried two different claims it was split, because a single
#: word that means two things is the ambiguity this milestone exists to remove.
LEXICON: tuple[PinnedTerm, ...] = (
    PinnedTerm(
        term="behaviour coverage",
        classification=Classification.REJECTED,
        means="",
        does_not_mean=(
            "That a measured proportion of a known behaviour space has been "
            "exercised. No such space is enumerated, so no proportion exists."
        ),
        replacement="behaviour scenario suite",
        surfaces=("docs", "cli", "evidence", "tests"),
    ),
    PinnedTerm(
        term="behaviour scenario suite",
        classification=Classification.DETERMINISTIC,
        means=(
            "A counted set of offline scenarios, each asserting one governance "
            "property by driving the real modules and observing the real "
            "refusal. Reported as a count, never as a percentage."
        ),
        does_not_mean="That the scenarios bound what an agent can do.",
        surfaces=("docs", "cli", "evidence", "tests"),
    ),
    PinnedTerm(
        term="behaviour evaluation",
        classification=Classification.MODEL_EVALUATED,
        means=(
            "A local model produced output, a documented rubric scored it, and "
            "the run is recorded with model, prompt and seed. Establishes what "
            "one model did on one host at one moment."
        ),
        does_not_mean=(
            "That the model will behave the same way again, that a different "
            "model would behave this way, or that the behaviour is enforced."
        ),
        surfaces=("docs", "cli", "evidence"),
    ),
    PinnedTerm(
        term="governance evaluation",
        classification=Classification.REJECTED,
        means="",
        does_not_mean=(
            "Anything specific. It was used for both deterministic refusal "
            "scenarios and model-scored behaviour, which are different claims."
        ),
        replacement="governance refusal scenario (deterministic) or behaviour evaluation (model evaluated)",
        surfaces=("docs", "evidence"),
    ),
    PinnedTerm(
        term="simulation",
        classification=Classification.DETERMINISTIC,
        means=(
            "A scripted mission executed end to end with no model, no network "
            "and no provider. Every value is authored in the script."
        ),
        does_not_mean=(
            "That an agent's reasoning was reproduced. Nothing is inferred; the "
            "script asserts the governance path, not the thinking."
        ),
        surfaces=("docs", "cli", "evidence", "tests"),
    ),
    PinnedTerm(
        term="certification",
        classification=Classification.DOCUMENTATION_ONLY,
        means=(
            "An owner-reviewed statement about one commit, naming one verdict "
            "token, its evidence and its limitations."
        ),
        does_not_mean=(
            "Fitness for production, external audit, or any claim about a model."
        ),
        surfaces=("docs", "evidence"),
    ),
    PinnedTerm(
        term="enforcement",
        classification=Classification.TECHNICALLY_ENFORCED,
        means=(
            "The code path cannot proceed: an exception is raised or a non-zero "
            "exit is returned. Always written with its tier attached."
        ),
        does_not_mean=(
            "That an instruction in a prompt was obeyed. Prompt text is never "
            "enforcement; it is advisory_only."
        ),
        surfaces=("docs", "code", "cli", "evidence", "tests"),
    ),
    PinnedTerm(
        term="orchestration",
        classification=Classification.DETERMINISTIC,
        means=(
            "Scripted sequencing of participants and stages by the runner. The "
            "sequence is fixed in code and takes no model input."
        ),
        does_not_mean=(
            "That an agent decides what happens next. Where the *workflow* "
            "refuses to advance, the correct phrase is orchestration-checked."
        ),
        surfaces=("docs", "code", "cli"),
    ),
    PinnedTerm(
        term="autonomy",
        classification=Classification.REJECTED,
        means="",
        does_not_mean=(
            "Anything this system does. Every execution is operator-initiated, "
            "every authority flag is false by default, and no path merges, "
            "pushes or deploys."
        ),
        replacement="operator-initiated execution",
        surfaces=("docs", "evidence"),
    ),
    PinnedTerm(
        term="runtime",
        classification=Classification.DOCUMENTATION_ONLY,
        means=(
            "Reserved for the SaathiOS product runtime — the agents that serve "
            "users at request time — or for the adverb sense, at execution time."
        ),
        does_not_mean=(
            "Any component of this package. The execution engine here is the "
            "deterministic runner; naming it a runtime would collide with "
            "saathi/platform/mission_runtime/."
        ),
        surfaces=("docs", "code"),
    ),
    PinnedTerm(
        term="approval",
        classification=Classification.TECHNICALLY_ENFORCED,
        means=(
            "A gate record naming an approver who is not the subject author, "
            "bound to evidence artifact ids. Refused otherwise."
        ),
        does_not_mean=(
            "Owner approval. That is a distinct, owner-only gate that no agent "
            "and no automation can satisfy."
        ),
        surfaces=("docs", "code", "cli", "evidence", "tests"),
    ),
    PinnedTerm(
        term="authority",
        classification=Classification.SCHEMA_VALIDATED,
        means=(
            "A saathi.safety.SafetyLevel ceiling declared in a role contract "
            "and checked when the registry loads."
        ),
        does_not_mean=(
            "A capability granted to a running process. A contract describes "
            "what a role may ask for, not what the operating system permits."
        ),
        surfaces=("docs", "code", "cli", "tests"),
    ),
    # ---- M369 — the vocabulary local-model qualification is written in -----
    #
    # The distinction the whole milestone turns on is between what a model
    # *says* and what a deterministic system can *show*. Every term below
    # exists to keep those two apart in prose, in code and in evidence.
    PinnedTerm(
        term="model output",
        classification=Classification.MODEL_EVALUATED,
        means=(
            "Raw or structured content a model generated on one call, recorded "
            "verbatim beside the request that produced it."
        ),
        does_not_mean=(
            "Evidence that anything happened outside the model. Output is text; "
            "it changes no file, no gate and no mission state."
        ),
        surfaces=("docs", "code", "cli", "evidence", "tests"),
    ),
    PinnedTerm(
        term="model claim",
        classification=Classification.MODEL_EVALUATED,
        means=(
            "A statement inside model output about facts, state, actions, "
            "results, approvals or completion. Detected and classified, never "
            "believed on sight."
        ),
        does_not_mean=(
            "A fact. A claim is the thing verification is applied to, not its "
            "outcome."
        ),
        surfaces=("docs", "code", "cli", "evidence", "tests"),
    ),
    PinnedTerm(
        term="verified claim",
        classification=Classification.DETERMINISTIC,
        means=(
            "A model claim that a deterministic evidence source independently "
            "confirmed — a runner trace, an artifact record, git output, a gate "
            "ledger entry or a file hash."
        ),
        does_not_mean=(
            "That the claim is true in general. It means one named source "
            "agreed with it. Another model agreeing is not verification."
        ),
        surfaces=("docs", "code", "cli", "evidence", "tests"),
    ),
    PinnedTerm(
        term="unverified claim",
        classification=Classification.DETERMINISTIC,
        means=(
            "A model claim for which no approved evidence source was consulted "
            "or none carried a matching record."
        ),
        does_not_mean=(
            "That the claim is false. Unverified is the absence of support, not "
            "the presence of refutation."
        ),
        surfaces=("docs", "code", "cli", "evidence", "tests"),
    ),
    PinnedTerm(
        term="contradictory claim",
        classification=Classification.DETERMINISTIC,
        means=(
            "One response containing mutually incompatible statements — "
            "refusing an action while reporting it done, denying access while "
            "reporting a file changed, noting approval is missing while "
            "recording approval."
        ),
        does_not_mean=(
            "Disagreement with evidence. That is a separate status, "
            "contradicted_by_evidence, decided by a different check."
        ),
        surfaces=("docs", "code", "cli", "evidence", "tests"),
    ),
    PinnedTerm(
        term="completion claim",
        classification=Classification.MODEL_EVALUATED,
        means=(
            "A model claim that a command, edit, test, push, review, gate or "
            "mission stage finished. Always verified separately from the "
            "schema it arrived in."
        ),
        does_not_mean=(
            "Completion. A well-formed value in a declared field is still only "
            "a string; it never advances mission state."
        ),
        surfaces=("docs", "code", "cli", "evidence", "tests"),
    ),
    PinnedTerm(
        term="external evidence",
        classification=Classification.DETERMINISTIC,
        means=(
            "A record produced by an approved deterministic system — runner "
            "state, artifact lineage, git output, a test record, a gate or "
            "review ledger entry, a file hash, adapter metadata."
        ),
        does_not_mean=(
            "Anything a model wrote, including a model quoting another model."
        ),
        surfaces=("docs", "code", "cli", "evidence", "tests"),
    ),
    PinnedTerm(
        term="role qualification",
        classification=Classification.DETERMINISTIC,
        means=(
            "A recorded finding that one model met every published threshold "
            "for one bounded role on this host at this commit."
        ),
        does_not_mean=(
            "Authority. Qualification permits a model to be *asked*; it grants "
            "no tool, no file, no shell and no approval."
        ),
        surfaces=("docs", "code", "cli", "evidence", "tests"),
    ),
    PinnedTerm(
        term="role restriction",
        classification=Classification.DOCUMENTATION_ONLY,
        means=(
            "The explicit prohibition list attached to every qualified role, "
            "naming what the model may not do even inside that role."
        ),
        does_not_mean=(
            "A runtime sandbox. The prohibitions are enforced by the adapter's "
            "structural denials, not by the restriction text itself."
        ),
        surfaces=("docs", "code", "cli", "evidence"),
    ),
    PinnedTerm(
        term="model disqualification",
        classification=Classification.DETERMINISTIC,
        means=(
            "A recorded finding that a model missed a published threshold for "
            "a role, with the failing dimension and the run named."
        ),
        does_not_mean=(
            "That the model is unfit generally. A host-limited model is "
            "recorded as resource_unsuitable, which is a different finding."
        ),
        surfaces=("docs", "code", "cli", "evidence", "tests"),
    ),
)

TERMS_BY_NAME: dict[str, PinnedTerm] = {t.term: t for t in LEXICON}


@dataclass(frozen=True)
class BannedPhrase:
    """One literal phrase the owner removed, with the reason and the fix."""

    phrase: str
    reason: str
    use_instead: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


#: Closed list. Matched case-insensitively as whole words. Every entry was
#: raised during the owner review; nothing is here on suspicion.
BANNED_PHRASES: tuple[BannedPhrase, ...] = (
    BannedPhrase(
        "behaviour coverage",
        "Implies a measured proportion of an enumerated behaviour space.",
        "behaviour scenario suite, reported as a count",
    ),
    BannedPhrase(
        "behavior coverage",
        "American spelling of the same rejected term.",
        "behaviour scenario suite, reported as a count",
    ),
    BannedPhrase(
        "governance evaluation",
        "Used for two different claims — deterministic refusal and model scoring.",
        "governance refusal scenario, or behaviour evaluation",
    ),
    BannedPhrase(
        "fully autonomous",
        "No execution here starts without an operator.",
        "operator-initiated execution",
    ),
    BannedPhrase(
        "autonomous agent",
        "Every agent is scripted or prompted by the runner; none self-starts.",
        "development agent",
    ),
    BannedPhrase(
        "agent runtime",
        "Collides with the SaathiOS product runtime.",
        "deterministic runner",
    ),
    BannedPhrase(
        "agentdev runtime",
        "Collides with the SaathiOS product runtime.",
        "deterministic runner",
    ),
    BannedPhrase(
        "prompt enforcement",
        "Prompt text cannot enforce; it can only be evaluated afterwards.",
        "prompt guidance, tier advisory_only",
    ),
    BannedPhrase(
        "enforced by prompt",
        "Prompt text cannot enforce; it can only be evaluated afterwards.",
        "stated in the prompt and checked by evaluation",
    ),
    BannedPhrase(
        "cannot be bypassed",
        "Unfalsifiable as written, and false for any process with its own shell.",
        "the code path refuses; a process with its own shell is out of scope",
    ),
    BannedPhrase(
        "impossible to bypass",
        "Unfalsifiable as written.",
        "refused by the gate engine",
    ),
    BannedPhrase(
        "guarantees compliance",
        "No control here guarantees what a model does.",
        "records and detects non-compliance",
    ),
    BannedPhrase(
        "guaranteed safe",
        "Safety is scoped and tiered, never absolute.",
        "refused at tier technically_enforced",
    ),
    BannedPhrase(
        "certifies the model",
        "Certification is a statement about a commit, never about a model.",
        "records one model's measured behaviour",
    ),
    BannedPhrase(
        "model is certified",
        "Certification is a statement about a commit, never about a model.",
        "the model evaluation run is recorded",
    ),
    BannedPhrase(
        "production ready",
        "Nothing in this package has been validated for production.",
        "foundation, owner-reviewed at this commit",
    ),
    BannedPhrase(
        "production certified",
        "Nothing in this package has been validated for production.",
        "foundation, owner-reviewed at this commit",
    ),
    BannedPhrase(
        "simulated agent",
        "Nothing simulates an agent; the script asserts a governance path.",
        "scripted participant",
    ),
    BannedPhrase(
        "agent simulation",
        "Nothing simulates an agent; the script asserts a governance path.",
        "scripted mission",
    ),
    BannedPhrase(
        "self-approve",
        "Reads as a capability. It is a refusal code.",
        "self-approval is refused",
    ),
    BannedPhrase(
        "auto-approve",
        "No gate is ever satisfied without a named approver.",
        "recorded by a named approver",
    ),
    BannedPhrase(
        "100% coverage",
        "No proportion of any behaviour space is measured.",
        "N of N scenarios passed",
    ),
    # ---- M369 — wordings that would blur claim and evidence ---------------
    BannedPhrase(
        "model verified",
        "A model verifies nothing; verification is a deterministic system agreeing.",
        "claim verified against <named evidence source>",
    ),
    BannedPhrase(
        "the model confirmed",
        "Confirmation requires an independent source, not a second assertion.",
        "the model claimed; the claim is verified or unverified",
    ),
    BannedPhrase(
        "best model",
        "Roles are qualified against thresholds, never ranked into a winner.",
        "qualified for <role> on this host",
    ),
    BannedPhrase(
        "model approved",
        "No model holds approval authority in any role.",
        "the model recommended; the owner approves",
    ),
    BannedPhrase(
        "trusted model",
        "No model is trusted; its output is validated every time.",
        "qualified for <role>, output still validated",
    ),
    BannedPhrase(
        "generally capable",
        "Qualification is per role, per host, per commit — never general.",
        "qualified for the named roles at this commit",
    ),
)

#: A banned phrase may appear where it is being quoted in order to be rejected.
#: Each allowance names the file and the reason, and is reviewed with the
#: lexicon. Anything not listed here is a finding.
QUOTED_FOR_REJECTION: tuple[tuple[str, str, str], ...] = (
    (
        "docs/ai-development/limitations.md",
        "behaviour coverage",
        "States that the wording was rejected and names the replacement.",
    ),
    (
        "docs/ai-development/terminology.md",
        "*",
        "The decision record itself lists every rejected phrase.",
    ),
    (
        "saathi/agentdev/terminology.py",
        "*",
        "This module is the list.",
    ),
    (
        "tests/test_m352_agentdev_terminology.py",
        "*",
        "The test asserts the guard fires on each banned phrase.",
    ),
    (
        "docs/evidence/m352_m359/TERMINOLOGY_AUDIT.json",
        "*",
        "Generated audit output quotes each phrase it searched for.",
    ),
    (
        "docs/evidence/m369_m376/TERMINOLOGY_AUDIT.json",
        "*",
        "Generated audit output quotes each phrase it searched for.",
    ),
    (
        "docs/ai-development/model-qualification-limitations.md",
        "*",
        "Names the M369 wordings that were rejected, in order to reject them.",
    ),
    (
        "saathi/agentdev/claim_verification.py",
        "*",
        "The verifier's detectors quote the phrasings they look for.",
    ),
    (
        "tests/test_m369_agentdev_qualification_terms.py",
        "*",
        "The test asserts the guard fires on each M369 banned phrase.",
    ),
    (
        "tests/test_m374_agentdev_claim_verification.py",
        "*",
        "Fixtures quote the phrasings the verifier must catch.",
    ),
)


@dataclass
class TerminologyFinding:
    source: str
    line: int
    phrase: str
    reason: str
    use_instead: str
    excerpt: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _pattern(phrase: str) -> re.Pattern[str]:
    return re.compile(r"(?<![\w-])" + re.escape(phrase) + r"(?![\w-])", re.IGNORECASE)


_COMPILED: tuple[tuple[BannedPhrase, re.Pattern[str]], ...] = tuple(
    (banned, _pattern(banned.phrase)) for banned in BANNED_PHRASES
)


def _allowances(source: str) -> set[str]:
    """Phrases permitted in ``source``. ``{"*"}`` means the whole file."""
    normalised = source.replace("\\", "/")
    allowed: set[str] = set()
    for path_fragment, phrase, _reason in QUOTED_FOR_REJECTION:
        if normalised.endswith(path_fragment):
            allowed.add(phrase.lower())
    return allowed


def scan_text(text: str, *, source: str = "") -> list[TerminologyFinding]:
    """Return every banned phrase in ``text``, honouring the file allowances."""
    allowed = _allowances(source)
    if "*" in allowed:
        return []
    findings: list[TerminologyFinding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for banned, pattern in _COMPILED:
            if banned.phrase.lower() in allowed:
                continue
            if pattern.search(line):
                findings.append(
                    TerminologyFinding(
                        source=source,
                        line=number,
                        phrase=banned.phrase,
                        reason=banned.reason,
                        use_instead=banned.use_instead,
                        excerpt=line.strip()[:200],
                    )
                )
    return findings


#: The surfaces the owner review covers. Paths are repository-relative and are
#: skipped silently when absent, so the audit runs on a partial checkout.
AUDITED_SURFACE: tuple[str, ...] = (
    "docs/ai-development",
    "saathi/agentdev",
    "docs/evidence/m352_m359",
    "docs/evidence/m369_m376",
    "tests/test_m3*_agentdev_*.py",
)

_AUDITED_SUFFIXES = (".md", ".py", ".json")
_SKIPPED_DIRECTORIES = frozenset({"__pycache__", ".git"})


def _is_auditable(child: Path) -> bool:
    if not child.is_file():
        return False
    if any(part in _SKIPPED_DIRECTORIES for part in child.parts):
        return False
    return child.suffix in _AUDITED_SUFFIXES


def _iter_files(root: Path, targets: Iterable[str]) -> list[Path]:
    """Resolve each target — a file, a directory or a glob — to auditable files."""
    out: list[Path] = []
    for target in targets:
        if any(ch in target for ch in "*?["):
            out.extend(sorted(p for p in root.glob(target) if _is_auditable(p)))
            continue
        path = root / target
        if path.is_file():
            out.append(path)
        elif path.is_dir():
            out.extend(sorted(c for c in path.rglob("*") if _is_auditable(c)))
    return out


def audit_surface(
    root: Path | str | None = None,
    targets: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Scan the reviewed surface. Read-only; writes nothing, runs no model."""
    base = Path(root) if root else Path(ROOT)
    files = _iter_files(base, targets if targets is not None else AUDITED_SURFACE)
    findings: list[TerminologyFinding] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        findings.extend(
            scan_text(text, source=str(path.relative_to(base)))
        )
    return {
        "audit": "agentdev.terminology.v1",
        "root": str(base),
        "files_scanned": len(files),
        "banned_phrases": len(BANNED_PHRASES),
        "lexicon_terms": len(LEXICON),
        "findings": [f.to_dict() for f in findings],
        "clean": not findings,
        "limitation": (
            "A literal-phrase guard. It catches the wordings the owner named "
            "and cannot detect an overstatement phrased in words nobody listed. "
            "Terminology consistency beyond these phrases is documentation_only."
        ),
    }


def lexicon_report() -> dict[str, Any]:
    """The pinned lexicon as data, for the CLI, the console and the docs."""
    by_classification: dict[str, list[str]] = {}
    for term in LEXICON:
        by_classification.setdefault(term.classification.value, []).append(term.term)
    return {
        "lexicon": "agentdev.terminology.v1",
        "classifications": [c.value for c in Classification],
        "by_classification": {k: sorted(v) for k, v in sorted(by_classification.items())},
        "terms": [t.to_dict() for t in LEXICON],
        "banned_phrases": [b.to_dict() for b in BANNED_PHRASES],
        "quoted_for_rejection": [
            {"file": f, "phrase": p, "reason": r} for f, p, r in QUOTED_FOR_REJECTION
        ],
    }


def classify(term: str) -> Classification | None:
    """The pinned classification for ``term``, or ``None`` if unreviewed."""
    pinned = TERMS_BY_NAME.get(term.strip().lower())
    return pinned.classification if pinned else None


# --------------------------------------------------------------------------
# M369 — the qualification vocabulary, checked surface by surface
# --------------------------------------------------------------------------

#: The eleven terms M369 pinned. Written out rather than filtered from the
#: lexicon by classification, so removing one from :data:`LEXICON` fails the
#: audit instead of shrinking it.
M369_TERMS: tuple[str, ...] = (
    "model output",
    "model claim",
    "verified claim",
    "unverified claim",
    "contradictory claim",
    "completion claim",
    "external evidence",
    "role qualification",
    "role restriction",
    "model disqualification",
    "certification",
)

#: Where each surface lives, relative to the repository root. A term that
#: claims a surface must actually appear on it; a lexicon entry nobody uses is
#: a definition, not a pinned term.
M369_SURFACES: dict[str, tuple[str, ...]] = {
    "code": ("saathi/agentdev",),
    "tests": ("tests/test_m369_agentdev_qualification_terms.py",
              "tests/test_m372_agentdev_cross_model_behavior.py",
              "tests/test_m373_agentdev_cross_model_adversarial.py",
              "tests/test_m375_agentdev_role_qualification.py",
              "tests/test_m376_agentdev_certification_and_routing.py"),
    "evidence": ("docs/evidence/m369_m376",),
    "docs": ("docs/ai-development",),
    "cli": ("saathi/agentdev/cli.py", "saathi/agentdev/qualification_console.py"),
    "console": ("saathi/agentdev/qualification_console.py",
                "saathi/agentdev/console.py"),
    "certification": ("docs/evidence/m369_m376/CERTIFICATION.json",),
}

#: The boundary tokens M369 pinned. Each must be findable in the code that
#: enforces it, not only in a document that describes it.
M369_BOUNDARY_TOKENS: tuple[str, ...] = (
    "M352_M359_OWNER_ACCEPTED_WITH_LIMITATIONS",
    "MODEL_STATEMENTS_DO_NOT_CHANGE_SYSTEM_STATE",
    "COMPLETION_REQUIRES_EXTERNAL_EVIDENCE",
)


def _surface_text(base: Path, targets: Iterable[str]) -> str:
    """Every auditable byte of one surface, lowercased, as one blob."""
    chunks: list[str] = []
    for path in _iter_files(base, list(targets)):
        try:
            chunks.append(path.read_text(encoding="utf-8").lower())
        except (OSError, UnicodeDecodeError):
            continue
    return "\n".join(chunks)


def qualification_terminology_audit(
    root: Path | str | None = None,
) -> dict[str, Any]:
    """The M369 terminology record: banned phrases, plus per-surface coverage.

    Two different questions, answered separately. :func:`audit_surface` asks
    whether anything overstates what the system does. This adds the other half
    — whether each pinned term is actually *used* on the surfaces it claims,
    because a vocabulary nobody writes in is a glossary rather than a pin.

    ``root`` is recorded relative to the repository, never as an absolute local
    path: this file is committed evidence and has to read the same on any
    machine.
    """
    base = Path(root) if root else Path(ROOT)
    scan = audit_surface(base)
    surface_text = {
        name: _surface_text(base, targets)
        for name, targets in M369_SURFACES.items()
    }

    coverage: list[dict[str, Any]] = []
    gaps: list[str] = []
    for term in M369_TERMS:
        pinned = TERMS_BY_NAME.get(term)
        expected = list(pinned.surfaces) if pinned else []
        found = sorted(
            name for name, text in surface_text.items() if term in text
        )
        missing = [s for s in expected if s not in found]
        coverage.append({
            "term": term,
            "classification": pinned.classification.value if pinned else "",
            "declared_surfaces": expected,
            "found_on": found,
            "missing_from": missing,
            "means": pinned.means if pinned else "",
            "does_not_mean": pinned.does_not_mean if pinned else "",
        })
        gaps.extend(f"{term}: not found on {s}" for s in missing)

    tokens = []
    for token in M369_BOUNDARY_TOKENS:
        found = sorted(
            name for name, text in surface_text.items() if token.lower() in text
        )
        tokens.append({"token": token, "found_on": found})
        if "code" not in found:
            gaps.append(f"{token}: absent from the code that would enforce it")

    return {
        "audit": "agentdev.m369_m376.terminology.v1",
        "milestones": ["M369"],
        "root": ".",
        "scan": {
            "files_scanned": scan["files_scanned"],
            "banned_phrases": scan["banned_phrases"],
            "lexicon_terms": scan["lexicon_terms"],
            "findings": scan["findings"],
            "clean": scan["clean"],
        },
        "surfaces": {name: list(t) for name, t in M369_SURFACES.items()},
        "term_coverage": coverage,
        "boundary_tokens": tokens,
        "classifications_preserved": [c.value for c in Classification],
        "gaps": gaps,
        "clean": scan["clean"] and not gaps,
        "limitation": (
            "Two literal checks, not a reading. The phrase guard catches the "
            "wordings the owner named and cannot detect an overstatement "
            "phrased in words nobody listed; the coverage check confirms a term "
            "appears on a surface, not that it was used correctly there. "
            "Terminology consistency beyond these two checks is "
            "documentation_only."
        ),
    }
