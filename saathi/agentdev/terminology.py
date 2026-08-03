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
