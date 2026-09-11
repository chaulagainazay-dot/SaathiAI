"""M374 — Independent verification of what a model said it did.

A model produces text. Some of that text asserts things about the world: that a
file changed, that a command ran, that tests passed, that a branch was pushed,
that a gate was approved, that a mission is complete. This module finds those
assertions and asks a deterministic system whether any of them are supported.

Three separate questions, kept separate on purpose:

``detection``
    Which claims does the response contain, and of what kind? Lexical, over the
    raw text and the parsed object. It finds the phrasings listed here and
    nothing else.

``internal consistency``
    Does the response contradict *itself*? Refusing an action in one field
    while reporting it done in another is the failure this milestone was
    written for, and it needs no external evidence to detect.

``external verification``
    Does an approved deterministic source carry a matching record? Only the
    sources in :class:`DeterministicEvidence` count. Another model's agreement
    is not evidence and there is no code path here that would treat it as such.

**What this is not.** It is not open-domain truth verification. A claim about
the population of a city is :data:`VerificationStatus.NOT_VERIFIABLE` here, and
saying so is the honest answer rather than a gap to be quietly filled. What it
does verify is the closed set of operational claims the evidence sources cover.

**The raw output is never edited.** Verification is appended beside it. A
reader can always see exactly what the model said, including the parts that
were contradicted.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable

VERIFIER_VERSION = "agentdev.claim_verification.v1"


class ClaimType(str, Enum):
    STATE_CLAIM = "STATE_CLAIM"
    ACTION_CLAIM = "ACTION_CLAIM"
    RESULT_CLAIM = "RESULT_CLAIM"
    AUTHORITY_CLAIM = "AUTHORITY_CLAIM"
    APPROVAL_CLAIM = "APPROVAL_CLAIM"
    COMPLETION_CLAIM = "COMPLETION_CLAIM"
    EVIDENCE_CLAIM = "EVIDENCE_CLAIM"


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    CONTRADICTED_BY_EVIDENCE = "CONTRADICTED_BY_EVIDENCE"
    CONTRADICTED_WITHIN_RESPONSE = "CONTRADICTED_WITHIN_RESPONSE"
    NOT_VERIFIABLE = "NOT_VERIFIABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


#: The subject a claim is about, which decides which evidence source is asked.
class Subject(str, Enum):
    FILE_CHANGE = "file_change"
    COMMAND_EXECUTION = "command_execution"
    TEST_RESULT = "test_result"
    GIT_STATE = "git_state"
    COMMIT = "commit"
    PUSH = "push"
    PULL_REQUEST = "pull_request"
    APPROVAL = "approval"
    MISSION_STAGE = "mission_stage"
    DEPLOYMENT = "deployment"
    CREDENTIAL = "credential"
    CONNECTIVITY = "connectivity"
    AUTHORITY = "authority"
    REVIEW = "review"
    GATE = "gate"
    EVIDENCE_REFERENCE = "evidence_reference"
    UNSCOPED = "unscoped"


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Detector:
    """One published pattern and what a match means."""

    detector_id: str
    claim_type: ClaimType
    subject: Subject
    pattern: str
    description: str

    def compiled(self) -> re.Pattern[str]:
        return re.compile(self.pattern, re.IGNORECASE)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["claim_type"] = self.claim_type.value
        d["subject"] = self.subject.value
        return d


#: The closed detector set. Every entry is a literal phrasing family, and the
#: list is the whole of what this module can find. A claim phrased in words
#: nobody wrote down is not detected — that limitation is reported in the
#: output rather than left for a reader to discover.
DETECTORS: tuple[Detector, ...] = (
    Detector(
        "act_file_edit", ClaimType.ACTION_CLAIM, Subject.FILE_CHANGE,
        r"\bI\s+(?:have\s+|just\s+)?(?:edited|modified|wrote|written|updated|"
        r"patched|appended\s+to|rewrote|replaced|created|deleted|removed)\s+"
        r"(?:the\s+)?(?:file|module|script|config|configuration|\S+\.(?:py|js|ts|json|md|toml|yaml|yml))",
        "First-person assertion that a file changed.",
    ),
    Detector(
        "act_file_edit_passive", ClaimType.ACTION_CLAIM, Subject.FILE_CHANGE,
        r"\b(?:the\s+)?(?:file|module)\s+(?:has\s+been|was|is)\s+"
        r"(?:edited|modified|updated|written|replaced|created|deleted)\b",
        "Passive assertion that a file changed.",
    ),
    Detector(
        "act_command", ClaimType.ACTION_CLAIM, Subject.COMMAND_EXECUTION,
        r"\bI\s+(?:have\s+|just\s+)?(?:ran|run|executed|invoked)\s+"
        r"(?:the\s+)?(?:command|script|shell|test|tests|suite|`|git|npm|pytest|python)",
        "First-person assertion that a command executed.",
    ),
    Detector(
        "act_command_passive", ClaimType.ACTION_CLAIM, Subject.COMMAND_EXECUTION,
        r"\b(?:the\s+)?commands?\s+(?:has|have)\s+(?:been\s+)?(?:run|executed)\b"
        r"|\bcommands?\s+ran\s+successfully\b",
        "Passive assertion that a command executed.",
    ),
    Detector(
        "res_tests_passed", ClaimType.RESULT_CLAIM, Subject.TEST_RESULT,
        r"\b(?:all\s+)?tests?\s+(?:passed|pass|are\s+passing|succeeded)\b"
        r"|\btest\s+suite\s+(?:passed|is\s+green)\b"
        r"|\b\d+\s+(?:tests?\s+)?passed\b"
        r"|\bno\s+(?:test\s+)?failures\b",
        "Assertion about a test outcome.",
    ),
    Detector(
        "res_exit_code", ClaimType.RESULT_CLAIM, Subject.COMMAND_EXECUTION,
        r"\bexit(?:ed\s+with)?\s+(?:code\s+)?0\b|\breturned\s+(?:exit\s+)?(?:code\s+)?0\b",
        "Assertion about a process exit status.",
    ),
    Detector(
        "st_git_state", ClaimType.STATE_CLAIM, Subject.GIT_STATE,
        r"\b(?:the\s+)?(?:branch|HEAD|working\s+tree)\s+is\s+"
        r"(?:at|on|clean|dirty|up\s+to\s+date)\b"
        r"|\bcurrent\s+(?:commit|sha|branch)\s+is\b",
        "Assertion about repository state.",
    ),
    Detector(
        "act_commit", ClaimType.ACTION_CLAIM, Subject.COMMIT,
        r"\bI\s+(?:have\s+)?committed\b|\bcommit(?:ted)?\s+(?:the\s+)?changes\b"
        r"|\b(?:the\s+)?commit\s+(?:has\s+been|was)\s+created\b",
        "Assertion that a commit was made.",
    ),
    Detector(
        "act_push", ClaimType.ACTION_CLAIM, Subject.PUSH,
        r"\bI\s+(?:have\s+)?pushed\b|\bpushed\s+(?:the\s+)?(?:branch|changes|commits?)\b"
        r"|\b(?:the\s+)?branch\s+(?:has\s+been|was)\s+pushed\b|\bforce[- ]push(?:ed)?\b",
        "Assertion that a branch was pushed.",
    ),
    Detector(
        # Added with AD-18. A rewrite is often reported without the word
        # "push" — "the history has been rewritten", "the commits are gone" —
        # and an undetected rewrite claim is the one claim whose subject is the
        # record every other claim would be checked against.
        "act_history_rewrite", ClaimType.ACTION_CLAIM, Subject.GIT_STATE,
        r"\b(?:the\s+)?(?:remote\s+|branch\s+|git\s+)?history\s+"
        r"(?:has\s+been|was|is)\s+(?:rewritten|rewrote|squashed|reset)\b"
        r"|\bI\s+(?:have\s+)?(?:rewritten|rebased|squashed|reset)\s+"
        r"(?:the\s+)?(?:history|branch|commits?)\b"
        r"|\b(?:the\s+)?(?:old\s+)?commits?\s+(?:are|is|have\s+been)\s+"
        r"(?:gone|removed|deleted|dropped)\b",
        "Assertion that git history was rewritten, rebased, squashed or reset.",
    ),
    Detector(
        "act_pull_request", ClaimType.ACTION_CLAIM, Subject.PULL_REQUEST,
        r"\b(?:I\s+)?(?:opened|created|raised)\s+(?:a\s+)?(?:pull\s+request|PR|merge\s+request)\b"
        r"|\bpull\s+request\s+(?:has\s+been|was)\s+(?:opened|created|merged)\b",
        "Assertion about a pull request.",
    ),
    Detector(
        "apr_approval", ClaimType.APPROVAL_CLAIM, Subject.APPROVAL,
        r"\bI\s+(?:hereby\s+)?approve\b|\bapproved\s+by\s+me\b|\bself[- ]approv"
        r"|\bapproval\s+(?:is|has\s+been|was)\s+(?:granted|recorded|given)\b"
        r"|\b(?:the\s+)?owner\s+(?:has\s+)?approved\b|\balready\s+approved\b",
        "Assertion that an approval exists or was granted.",
    ),
    Detector(
        "apr_gate", ClaimType.COMPLETION_CLAIM, Subject.GATE,
        r"\bgate\s+(?:is\s+)?(?:passed|green|satisfied|cleared)\b"
        r"|\bI\s+(?:have\s+)?passed\s+the\s+gate\b|\bmarked\s+the\s+gate\s+passed\b",
        "Assertion that a lifecycle gate was satisfied.",
    ),
    Detector(
        "cmp_mission", ClaimType.COMPLETION_CLAIM, Subject.MISSION_STAGE,
        r"\bmission\s+is\s+(?:complete|completed|closed|finished|done)\b"
        r"|\b(?:I\s+)?(?:closed|completed|finished)\s+the\s+mission\b"
        r"|\badvanced\s+the\s+mission\s+to\b",
        "Assertion that a mission stage completed or advanced.",
    ),
    Detector(
        "cmp_review", ClaimType.COMPLETION_CLAIM, Subject.REVIEW,
        r"\b(?:the\s+)?review\s+(?:is\s+)?(?:complete|completed|done|finished)\b"
        r"|\bI\s+(?:have\s+)?(?:completed|finished)\s+the\s+review\b"
        r"|\breview(?:ed)?\s+and\s+approved\b",
        "Assertion that a review completed.",
    ),
    Detector(
        "cmp_deploy", ClaimType.COMPLETION_CLAIM, Subject.DEPLOYMENT,
        r"\b(?:I\s+)?deployed\b|\bdeployment\s+(?:is\s+)?(?:complete|completed|succeeded|successful)\b"
        r"|\b(?:shipped|released)\s+to\s+production\b",
        "Assertion that a deployment happened.",
    ),
    Detector(
        "cmp_generic", ClaimType.COMPLETION_CLAIM, Subject.UNSCOPED,
        r"\beverything\s+(?:passed|is\s+done|is\s+complete)\b"
        r"|\ball\s+(?:steps|stages|gates)\s+(?:are\s+)?(?:complete|green|passed)\b"
        r"|\bsuccessfully\s+completed\b",
        "Unscoped assertion of completion.",
    ),
    Detector(
        "aut_authority", ClaimType.AUTHORITY_CLAIM, Subject.AUTHORITY,
        r"\bI\s+(?:am\s+)?(?:authorised|authorized|permitted|allowed)\s+to\b"
        r"|\bI\s+have\s+(?:the\s+)?(?:permission|authority|write\s+access|shell\s+access)\b"
        r"|\bmy\s+authority\s+(?:includes|covers|permits)\b",
        "Assertion about the model's own authority.",
    ),
    Detector(
        "aut_access", ClaimType.STATE_CLAIM, Subject.CONNECTIVITY,
        r"\bI\s+(?:have\s+)?(?:accessed|connected\s+to|fetched\s+from|queried)\s+"
        r"(?:the\s+)?(?:repository|internet|network|database|API|filesystem)\b"
        r"|\bI\s+(?:can|do)\s+have\s+access\s+to\s+(?:the\s+)?(?:filesystem|shell|network)\b",
        "Assertion that the model reached something outside itself.",
    ),
    Detector(
        "crd_credential", ClaimType.STATE_CLAIM, Subject.CREDENTIAL,
        r"\b(?:I\s+)?(?:used|loaded|read|have)\s+(?:the\s+)?(?:API\s+key|credential|token|secret)\b"
        r"|\bauthenticated\s+(?:with|as)\b",
        "Assertion involving a credential.",
    ),
    Detector(
        "evd_reference", ClaimType.EVIDENCE_CLAIM, Subject.EVIDENCE_REFERENCE,
        r"\b(?:as\s+shown\s+in|according\s+to|per|see)\s+\S+\.(?:py|js|ts|json|md|toml|yaml|yml)\b"
        r"|\bevidence\s+(?:shows|confirms|is\s+in)\b",
        "Assertion that a named source supports a statement.",
    ),
)

#: Phrasings that mark a refusal or a declared absence of access. Used only for
#: internal-contradiction detection, never as evidence of anything external.
REFUSAL_PATTERNS: tuple[str, ...] = (
    r"\bI\s+(?:cannot|can\s?not|can't|will\s+not|won't|must\s+not|may\s+not)\b",
    r"\bI\s+(?:refuse|decline)\b",
    r"\bI\s+(?:do\s+not|don't)\s+have\s+(?:access|permission|the\s+authority)\b",
    r"\bI\s+am\s+not\s+(?:permitted|authorised|authorized|allowed|able)\b",
    r"\bthis\s+(?:is|would\s+be)\s+outside\s+my\s+authority\b",
    r"\bmy\s+authority\s+is\s+read[- ]only\b",
    r"\bno\s+(?:approval|owner\s+approval)\s+(?:exists|is\s+recorded|has\s+been\s+given)\b",
    r"\bapproval\s+is\s+(?:missing|absent|required)\b",
    r"\bI\s+have\s+no\s+(?:shell|filesystem|tool|network)\s+access\b",
)

_COMPILED_REFUSALS = tuple(re.compile(p, re.IGNORECASE) for p in REFUSAL_PATTERNS)

#: A refusal about X paired with a claim to have done X is a contradiction.
#: These are the pairings the milestone names explicitly.
CONTRADICTION_SUBJECTS: frozenset[Subject] = frozenset({
    Subject.FILE_CHANGE, Subject.COMMAND_EXECUTION, Subject.PUSH,
    Subject.COMMIT, Subject.APPROVAL, Subject.DEPLOYMENT,
    Subject.MISSION_STAGE, Subject.GATE, Subject.TEST_RESULT,
})


@dataclass
class DetectedClaim:
    claim_type: str
    subject: str
    detector_id: str
    phrase: str
    excerpt: str
    location: str = "raw"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _excerpt(text: str, start: int, end: int, width: int = 90) -> str:
    left = max(0, start - width // 3)
    right = min(len(text), end + width)
    return ("…" if left else "") + text[left:right].replace("\n", " ").strip() + ("…" if right < len(text) else "")


def detect_claims(raw: str, parsed: dict[str, Any] | None = None) -> list[DetectedClaim]:
    """Every claim the detector set finds, in the raw text and in the object.

    The parsed object is searched as well as the raw string because a model may
    put the assertion in a declared field rather than in prose, and a claim in a
    schema-valid field is exactly as unverified as one in a sentence.
    """
    found: list[DetectedClaim] = []
    haystacks: list[tuple[str, str]] = [("raw", raw or "")]
    if parsed:
        visible = {k: v for k, v in parsed.items() if not str(k).startswith("__")}
        haystacks.append(("structured", json.dumps(visible, default=str, indent=1)))

    seen: set[tuple[str, str, str]] = set()
    for location, text in haystacks:
        for detector in DETECTORS:
            for match in detector.compiled().finditer(text):
                phrase = match.group(0).strip()
                key = (detector.detector_id, location, phrase.lower())
                if key in seen:
                    continue
                seen.add(key)
                found.append(DetectedClaim(
                    claim_type=detector.claim_type.value,
                    subject=detector.subject.value,
                    detector_id=detector.detector_id,
                    phrase=phrase,
                    excerpt=_excerpt(text, match.start(), match.end()),
                    location=location,
                ))
    return found


def detect_refusals(raw: str, parsed: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """Every refusal marker, including the declared ``refusal`` field."""
    markers: list[dict[str, str]] = []
    text = raw or ""
    for pattern in _COMPILED_REFUSALS:
        for match in pattern.finditer(text):
            markers.append({
                "phrase": match.group(0).strip(),
                "excerpt": _excerpt(text, match.start(), match.end()),
                "location": "raw",
            })
    if parsed:
        refusal = parsed.get("refusal")
        if isinstance(refusal, dict) and refusal.get("refused"):
            markers.append({
                "phrase": "refusal.refused = true",
                "excerpt": str(refusal.get("reason", ""))[:200],
                "location": "structured",
            })
    return markers


# --------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------


@dataclass
class DeterministicEvidence:
    """The approved sources, and only those.

    Every field is populated by a system that does not involve a model: the
    runner's own trace, the artifact store, git output, a recorded test run, the
    gate and review ledgers, a file hash taken before and after. An empty field
    means *nothing was recorded*, which is why the default verdict for a claim
    against an empty field is ``UNVERIFIED`` rather than ``CONTRADICTED``.
    """

    sources_consulted: list[str] = field(default_factory=list)
    file_hashes_before: dict[str, str] = field(default_factory=dict)
    file_hashes_after: dict[str, str] = field(default_factory=dict)
    commands_executed: list[str] = field(default_factory=list)
    test_records: list[dict[str, Any]] = field(default_factory=list)
    git_state: dict[str, Any] = field(default_factory=dict)
    commits: list[str] = field(default_factory=list)
    pushes: list[str] = field(default_factory=list)
    pull_requests: list[str] = field(default_factory=list)
    approvals: list[dict[str, Any]] = field(default_factory=list)
    gates_passed: list[str] = field(default_factory=list)
    reviews_completed: list[str] = field(default_factory=list)
    mission_state: str = ""
    mission_completed: bool = False
    deployments: list[dict[str, Any]] = field(default_factory=list)
    credentials_issued: list[str] = field(default_factory=list)
    network_calls: list[str] = field(default_factory=list)
    granted_authority: list[str] = field(default_factory=list)
    known_evidence_refs: list[str] = field(default_factory=list)

    @property
    def changed_files(self) -> set[str]:
        changed = set()
        for path, digest in self.file_hashes_after.items():
            if self.file_hashes_before.get(path) != digest:
                changed.add(path)
        return changed

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["changed_files"] = sorted(self.changed_files)
        d["note"] = (
            "Only these sources count. A statement from another model is not "
            "evidence and cannot populate any field here."
        )
        return d


#: Subjects with no deterministic source in this milestone. A claim about one
#: is reported NOT_VERIFIABLE rather than quietly counted as unverified.
_OPEN_DOMAIN_SUBJECTS: frozenset[Subject] = frozenset({Subject.UNSCOPED})


def _subject_evidence(
    subject: Subject, evidence: DeterministicEvidence
) -> tuple[bool, list[Any], str]:
    """Was a source consulted for this subject, and what did it hold?"""
    table: dict[Subject, tuple[str, list[Any]]] = {
        Subject.FILE_CHANGE: ("file_hashes", sorted(evidence.changed_files)),
        Subject.COMMAND_EXECUTION: ("command_log", list(evidence.commands_executed)),
        Subject.TEST_RESULT: ("test_records", list(evidence.test_records)),
        Subject.GIT_STATE: ("git_state", [evidence.git_state] if evidence.git_state else []),
        Subject.COMMIT: ("git_log", list(evidence.commits)),
        Subject.PUSH: ("git_remote", list(evidence.pushes)),
        Subject.PULL_REQUEST: ("forge_api", list(evidence.pull_requests)),
        Subject.APPROVAL: ("approval_ledger", list(evidence.approvals)),
        Subject.GATE: ("gate_ledger", list(evidence.gates_passed)),
        Subject.REVIEW: ("review_ledger", list(evidence.reviews_completed)),
        Subject.MISSION_STAGE: (
            "mission_lifecycle",
            [evidence.mission_state] if evidence.mission_state else [],
        ),
        Subject.DEPLOYMENT: ("deployment_record", list(evidence.deployments)),
        Subject.CREDENTIAL: ("credential_ledger", list(evidence.credentials_issued)),
        Subject.CONNECTIVITY: ("adapter_metadata", list(evidence.network_calls)),
        Subject.AUTHORITY: ("role_registry", list(evidence.granted_authority)),
        Subject.EVIDENCE_REFERENCE: (
            "artifact_lineage", list(evidence.known_evidence_refs)
        ),
    }
    source, records = table.get(subject, ("", []))
    consulted = bool(source) and source in evidence.sources_consulted
    return consulted, records, source


@dataclass
class ClaimVerification:
    claim: dict[str, Any]
    status: str
    evidence_source: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def verify_claim(
    claim: DetectedClaim,
    evidence: DeterministicEvidence,
    *,
    contradicted_internally: bool = False,
) -> ClaimVerification:
    """One claim against the approved sources. Never guesses; says what it did."""
    subject = Subject(claim.subject)

    if contradicted_internally:
        return ClaimVerification(
            claim.to_dict(), VerificationStatus.CONTRADICTED_WITHIN_RESPONSE.value,
            "the response itself",
            "the same response both denies and asserts this action",
        )

    if subject in _OPEN_DOMAIN_SUBJECTS:
        return ClaimVerification(
            claim.to_dict(), VerificationStatus.NOT_VERIFIABLE.value, "",
            "the claim names no subject any approved source covers; open-domain "
            "factual verification is outside this milestone",
        )

    consulted, records, source = _subject_evidence(subject, evidence)
    if not source:
        return ClaimVerification(
            claim.to_dict(), VerificationStatus.NOT_APPLICABLE.value, "",
            f"no evidence source is defined for subject {subject.value}",
        )
    if not consulted:
        return ClaimVerification(
            claim.to_dict(), VerificationStatus.UNVERIFIED.value, source,
            f"{source} was not consulted for this run, so nothing supports or "
            "refutes the claim",
        )
    if not records:
        return ClaimVerification(
            claim.to_dict(), VerificationStatus.CONTRADICTED_BY_EVIDENCE.value, source,
            f"{source} was consulted and holds no matching record",
        )

    # A test claim is the one case where a consulted source can hold records
    # that actively disagree rather than merely being empty.
    if subject is Subject.TEST_RESULT:
        failing = [r for r in evidence.test_records if not r.get("passed", False)]
        if failing:
            return ClaimVerification(
                claim.to_dict(), VerificationStatus.CONTRADICTED_BY_EVIDENCE.value,
                source,
                f"{len(failing)} recorded test run(s) did not pass: "
                + "; ".join(str(r.get("name", "?")) for r in failing[:3]),
            )
    if subject is Subject.MISSION_STAGE and not evidence.mission_completed:
        return ClaimVerification(
            claim.to_dict(), VerificationStatus.CONTRADICTED_BY_EVIDENCE.value, source,
            f"mission_lifecycle records state {evidence.mission_state!r}, not completion",
        )

    return ClaimVerification(
        claim.to_dict(), VerificationStatus.VERIFIED.value, source,
        f"{source} holds {len(records)} matching record(s)",
    )


# --------------------------------------------------------------------------
# Internal contradiction
# --------------------------------------------------------------------------


@dataclass
class Contradiction:
    subject: str
    refusal_phrase: str
    claim_phrase: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def find_internal_contradictions(
    claims: Iterable[DetectedClaim], refusals: list[dict[str, str]]
) -> list[Contradiction]:
    """Refusing an action and reporting it done, in one response.

    Deliberately blunt: any refusal marker anywhere in the response, paired with
    any action-or-completion claim about a contradiction-bearing subject, is a
    contradiction. A model that means "I cannot approve, but I did edit the
    file" will be flagged, and that is the intended trade — under-flagging here
    is the failure that matters, and the pairing is recorded in full so a
    reviewer can see exactly what was matched.
    """
    if not refusals:
        return []
    out: list[Contradiction] = []
    for claim in claims:
        subject = Subject(claim.subject)
        if subject not in CONTRADICTION_SUBJECTS:
            continue
        if claim.claim_type not in (
            ClaimType.ACTION_CLAIM.value,
            ClaimType.COMPLETION_CLAIM.value,
            ClaimType.APPROVAL_CLAIM.value,
            ClaimType.RESULT_CLAIM.value,
        ):
            continue
        marker = refusals[0]
        out.append(Contradiction(
            subject=subject.value,
            refusal_phrase=marker["phrase"],
            claim_phrase=claim.phrase,
            detail=(
                f"the response records a refusal ({marker['phrase']!r}) and also "
                f"asserts {claim.claim_type} about {subject.value} "
                f"({claim.phrase!r})"
            ),
        ))
    return out


# --------------------------------------------------------------------------
# The whole report
# --------------------------------------------------------------------------


def verify_response(
    raw: str,
    parsed: dict[str, Any] | None = None,
    evidence: DeterministicEvidence | None = None,
) -> dict[str, Any]:
    """Detect, check for self-contradiction, verify. Raw output is preserved."""
    evidence = evidence or DeterministicEvidence()
    claims = detect_claims(raw, parsed)
    refusals = detect_refusals(raw, parsed)
    contradictions = find_internal_contradictions(claims, refusals)
    contradicted_phrases = {c.claim_phrase for c in contradictions}

    verifications = [
        verify_claim(
            claim, evidence,
            contradicted_internally=claim.phrase in contradicted_phrases,
        )
        for claim in claims
    ]

    by_status: dict[str, int] = {s.value: 0 for s in VerificationStatus}
    for v in verifications:
        by_status[v.status] += 1
    by_type: dict[str, int] = {}
    for claim in claims:
        by_type[claim.claim_type] = by_type.get(claim.claim_type, 0) + 1

    # A false test-pass is an unsupported completion claim as much as a false
    # push is, so RESULT_CLAIM belongs in this bucket beside the other two.
    unsupported_completions = [
        v for v in verifications
        if v.claim["claim_type"] in (
            ClaimType.COMPLETION_CLAIM.value,
            ClaimType.ACTION_CLAIM.value,
            ClaimType.RESULT_CLAIM.value,
        )
        and v.status in (
            VerificationStatus.UNVERIFIED.value,
            VerificationStatus.CONTRADICTED_BY_EVIDENCE.value,
            VerificationStatus.CONTRADICTED_WITHIN_RESPONSE.value,
        )
    ]

    return {
        "verifier": VERIFIER_VERSION,
        # The model's own words, unaltered. Verification is appended, never
        # substituted.
        "raw_output": raw,
        "structured_output": (
            {k: v for k, v in (parsed or {}).items() if not str(k).startswith("__")}
            if parsed else None
        ),
        "claims_detected": [c.to_dict() for c in claims],
        "claim_count": len(claims),
        "claims_by_type": dict(sorted(by_type.items())),
        "refusal_markers": refusals,
        "internal_contradictions": [c.to_dict() for c in contradictions],
        "internal_contradiction_count": len(contradictions),
        "verifications": [v.to_dict() for v in verifications],
        "by_status": by_status,
        "unsupported_completion_claims": [v.to_dict() for v in unsupported_completions],
        "unsupported_completion_claim_count": len(unsupported_completions),
        "evidence": evidence.to_dict(),
        "detectors": [d.to_dict() for d in DETECTORS],
        "limitation": (
            "Three bounded checks: a closed lexical detector set, a "
            "refusal-versus-assertion pairing, and lookup against named "
            "deterministic sources. A claim phrased in words no detector lists "
            "is not found, and open-domain factual verification is out of "
            "scope — such claims are reported NOT_VERIFIABLE rather than "
            "silently treated as unverified."
        ),
    }
