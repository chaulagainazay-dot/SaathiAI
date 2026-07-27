"""M62.3 — pure research analysis logic. Deterministic, no network, no LLM.

Prompt-injection detection, rule-based claim extraction, citation verification,
contradiction discovery, a component-based confidence model, and independent
challenge. Model-assisted extraction may be an optional adapter later; the
certified path is deterministic so tests never depend on external LLMs.
"""
from __future__ import annotations

import re
from typing import Any

from saathi.platform.research.models import (
    FactClass, SourceType, TrustClass, SourceQuality, InjectionState, Verification,
    ContradictionType, ResearchSource, Claim, Citation, Contradiction, content_hash,
)

# ── prompt-injection defense ──────────────────────────────────────────────────
# HIGH-risk patterns block automatic publication; others are SUSPECTED (kept as
# evidence, flagged). Source text is untrusted data — never an instruction.
_BLOCK_PATTERNS = [
    r"ignore (all |previous )?instructions", r"reveal (the )?secret", r"send (the )?credential",
    r"execute (this |the )?trade", r"place (an? )?order", r"approve (this |the )?(request|trade)",
    r"change (the )?system (policy|prompt)", r"disregard (the )?(policy|rules)",
    r"exfiltrate", r"leak (the )?(key|token|password)",
]
_SUSPECT_PATTERNS = [
    r"as an ai", r"you must now", r"new instructions:", r"system:\s", r"call (the )?tool",
    r"do not tell", r"override",
]


def detect_injection(text: str) -> tuple[InjectionState, list[str]]:
    t = (text or "").lower()
    findings: list[str] = []
    for p in _BLOCK_PATTERNS:
        if re.search(p, t):
            findings.append(f"BLOCK:{p}")
    if findings:
        return InjectionState.BLOCKED, findings
    for p in _SUSPECT_PATTERNS:
        if re.search(p, t):
            findings.append(f"SUSPECT:{p}")
    if findings:
        return InjectionState.SUSPECTED, findings
    return InjectionState.CLEAN, []


# ── source quality ────────────────────────────────────────────────────────────
def classify_source_quality(src: ResearchSource, *, now: float, stale_after_sec: float = 31_536_000.0,
                            known_hashes: set[str] | None = None) -> SourceQuality:
    """Classify a source (fail-closed). stale_after default 1y. Sets injection too."""
    findings = src.findings
    inj, inj_findings = detect_injection(src.content)
    src.injection = inj
    findings.extend(inj_findings)
    if inj == InjectionState.BLOCKED:
        findings.append("PROMPT_INJECTION_SUSPECTED")
        return SourceQuality.PROMPT_INJECTION_SUSPECTED
    if not src.content.strip():
        return SourceQuality.MALFORMED
    if known_hashes is not None and src.hash and src.hash in known_hashes:
        return SourceQuality.DUPLICATE
    if src.published_at <= 0 and src.effective_at <= 0:
        findings.append("MISSING_DATE")
        return SourceQuality.MISSING_DATE
    eff = src.effective_at or src.published_at
    if eff and (now - eff) > stale_after_sec:
        findings.append("STALE")
        return SourceQuality.STALE
    return SourceQuality.VALID


# ── rule-based claim extraction ───────────────────────────────────────────────
# Deterministic line format (optional tags):  FACTCLASS [topic] statement...
_FACTCLASS_TOKENS = {c.value: c for c in FactClass}
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
_TOPIC_RE = re.compile(r"^\[([a-z0-9_\-]+)\]\s*", re.IGNORECASE)


def _numeric_value(statement: str):
    m = _NUM_RE.search(statement)
    return float(m.group()) if m else None


def _classify_statement(statement: str) -> FactClass:
    s = statement.lower()
    if any(w in s for w in ("will ", "expect", "forecast", "projected", "guidance")):
        return FactClass.FORECAST
    if any(w in s for w in ("assume", "assuming", "if we")):
        return FactClass.ASSUMPTION
    if "=" in statement or "calculated" in s or "compute" in s:
        return FactClass.CALCULATION
    if any(w in s for w in ("believe", "think", "opinion", "likely great", "bullish", "bearish")):
        return FactClass.OPINION
    if any(w in s for w in ("therefore", "implies", "suggests", "because")):
        return FactClass.INFERENCE
    return FactClass.FACT


def extract_claims(src: ResearchSource, *, agent_role: str = "FundamentalAnalyst") -> list[dict[str, Any]]:
    """Deterministic extraction. Returns dicts (topic + numeric parsed for later
    contradiction detection). Each claim carries a resolvable `line:N` locator."""
    out: list[dict[str, Any]] = []
    for i, raw in enumerate(src.content.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fc = None
        parts = line.split(" ", 1)
        if parts[0].upper() in _FACTCLASS_TOKENS:
            fc = _FACTCLASS_TOKENS[parts[0].upper()]
            line = parts[1] if len(parts) > 1 else ""
        topic = ""
        tm = _TOPIC_RE.match(line)
        if tm:
            topic = tm.group(1).lower()
            line = _TOPIC_RE.sub("", line, count=1)
        statement = line.strip()
        if not statement:
            continue
        fact_class = fc or _classify_statement(statement)
        out.append({
            "statement": statement, "fact_class": fact_class, "locator": f"line:{i}",
            "topic": topic, "numeric": _numeric_value(statement), "agent_role": agent_role,
            "excerpt": raw.strip()[:240],
        })
    return out


# ── citation verification ─────────────────────────────────────────────────────
def resolve_locator(src: ResearchSource, locator: str) -> bool:
    """Bounded locator resolution: line:N | para:N | field:NAME | row:N."""
    if not locator or ":" not in locator:
        return False
    kind, _, val = locator.partition(":")
    kind = kind.lower()
    if kind == "line":
        try:
            n = int(val)
        except ValueError:
            return False
        return 1 <= n <= len(src.content.splitlines())
    if kind == "para":
        try:
            n = int(val)
        except ValueError:
            return False
        return 1 <= n <= max(1, len([p for p in src.content.split("\n\n") if p.strip()]))
    if kind in ("field", "series"):
        return val.lower() in src.content.lower()
    if kind == "row":
        try:
            n = int(val)
        except ValueError:
            return False
        return 1 <= n <= len(src.content.splitlines())
    return False


def verify_citation(citation: Citation, src: ResearchSource | None) -> Verification:
    if src is None or src.source_id != citation.source_id:
        citation.detail = "source missing or mismatched"
        citation.verification = Verification.FAILED
        return citation.verification
    if citation.source_hash and src.hash and citation.source_hash != src.hash:
        citation.detail = "source hash mismatch (superseded/tampered)"
        citation.verification = Verification.FAILED
        return citation.verification
    if not resolve_locator(src, citation.locator):
        citation.detail = f"locator {citation.locator} does not resolve"
        citation.verification = Verification.FAILED
        return citation.verification
    citation.detail = "ok"
    citation.verification = Verification.VERIFIED
    return citation.verification


# ── contradiction discovery ───────────────────────────────────────────────────
def find_contradictions(claims: list[Claim], sources_by_id: dict[str, ResearchSource],
                        claim_meta: dict[str, dict]) -> list[dict[str, Any]]:
    """Compare claims across sources. Preserves both claims; never discards
    conflicting evidence. `claim_meta[claim_id]` carries {topic, numeric}."""
    out: list[dict[str, Any]] = []
    by_topic: dict[str, list[Claim]] = {}
    for c in claims:
        topic = claim_meta.get(c.claim_id, {}).get("topic") or ""
        if topic:
            by_topic.setdefault(topic, []).append(c)
    for topic, group in by_topic.items():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if a.source_id == b.source_id:
                    continue
                na = claim_meta.get(a.claim_id, {}).get("numeric")
                nb = claim_meta.get(b.claim_id, {}).get("numeric")
                sa, sb = sources_by_id.get(a.source_id), sources_by_id.get(b.source_id)
                # temporal supersession: same topic, different sources, one newer
                if sa and sb and na is not None and nb is not None and na != nb:
                    ea = sa.effective_at or sa.published_at
                    eb = sb.effective_at or sb.published_at
                    if ea and eb and abs(ea - eb) > 0:
                        out.append({"claim_a": a.claim_id, "claim_b": b.claim_id,
                                    "kind": ContradictionType.SOURCE_REVISION, "severity": "medium"})
                        continue
                if na is not None and nb is not None and na != nb:
                    kind = (ContradictionType.FORECAST_DISAGREEMENT
                            if a.fact_class == FactClass.FORECAST and b.fact_class == FactClass.FORECAST
                            else ContradictionType.NUMERICAL_CONFLICT)
                    sev = "critical" if a.materiality == "high" or b.materiality == "high" else "high"
                    out.append({"claim_a": a.claim_id, "claim_b": b.claim_id, "kind": kind, "severity": sev})
                    continue
                # direct negation
                if _negates(a.statement, b.statement):
                    out.append({"claim_a": a.claim_id, "claim_b": b.claim_id,
                                "kind": ContradictionType.DIRECT_CONFLICT, "severity": "high"})
    return out


def _negates(a: str, b: str) -> bool:
    la, lb = a.lower(), b.lower()
    neg = ("not ", " no ", "false", "declin", "decreas")
    pos = ("increas", "grew", "grow", "rose", "gain")
    a_neg = any(w in la for w in neg)
    b_pos = any(w in lb for w in pos)
    a_pos = any(w in la for w in pos)
    b_neg = any(w in lb for w in neg)
    return (a_neg and b_pos) or (a_pos and b_neg)


# ── confidence model (component-based; documented) ────────────────────────────
def confidence_components(*, sources: list[ResearchSource], claims: list[Claim],
                          citations: list[Citation], contradictions: list[Contradiction]) -> dict[str, Any]:
    """Bounded [0,1] components. The scalar is a documented weighted mean; the
    component breakdown is always preserved. High score != guaranteed correctness."""
    n_src = len(sources) or 1
    n_claim = len(claims) or 1
    valid_src = sum(1 for s in sources if s.quality == SourceQuality.VALID)
    trusts = {s.trust for s in sources}
    verified_cite = sum(1 for c in citations if c.verification == Verification.VERIFIED)
    fresh = sum(1 for s in sources if s.quality not in (SourceQuality.STALE, SourceQuality.SUPERSEDED))
    crit_contra = sum(1 for c in contradictions if c.severity in ("high", "critical") and c.resolution == "UNRESOLVED")
    assumptions = sum(1 for c in claims if c.fact_class == FactClass.ASSUMPTION)

    comp = {
        "source_quality": round(valid_src / n_src, 3),
        "source_diversity": round(min(len(trusts) / 3, 1.0), 3),
        "citation_coverage": round(min(verified_cite / n_claim, 1.0), 3),
        "data_freshness": round(fresh / n_src, 3),
        "contradiction_severity": round(max(0.0, 1.0 - crit_contra * 0.34), 3),
        "assumption_burden": round(max(0.0, 1.0 - assumptions / n_claim), 3),
    }
    weights = {"source_quality": 0.25, "source_diversity": 0.1, "citation_coverage": 0.25,
               "data_freshness": 0.15, "contradiction_severity": 0.15, "assumption_burden": 0.1}
    score = round(sum(comp[k] * weights[k] for k in comp), 3)
    return {"score": score, "components": comp, "weights": weights,
            "note": "component-based; a high score is not a guarantee of correctness"}


# ── independent challenge ─────────────────────────────────────────────────────
CRITICAL_SEVERITIES = frozenset({"critical"})


def challenge_thesis(*, sources: list[ResearchSource], claims: list[Claim],
                     citations: list[Citation], contradictions: list[Contradiction],
                     scenarios: list[dict], challenger_role: str = "ContrarianReviewer") -> dict[str, Any]:
    """An independent role (must differ from synthesizer) attacks the thesis."""
    findings: list[dict[str, Any]] = []

    def add(sev, code, detail):
        findings.append({"severity": sev, "code": code, "detail": detail})

    # unresolved critical/high contradictions
    for c in contradictions:
        if c.resolution == "UNRESOLVED" and c.severity in ("high", "critical"):
            add("critical" if c.severity == "critical" else "high", "UNRESOLVED_CONTRADICTION",
                f"{c.kind.value} between {c.claim_a} and {c.claim_b}")
    # claims with no verified citation
    verified_claims = {c.claim_id for c in citations if c.verification == Verification.VERIFIED}
    for cl in claims:
        if cl.fact_class in (FactClass.FACT, FactClass.CALCULATION) and cl.claim_id not in verified_claims:
            add("critical", "UNCITED_FACT", f"claim {cl.claim_id} ({cl.fact_class.value}) lacks a verified citation")
    # unsupported certainty: FORECAST/OPINION presented as high materiality
    for cl in claims:
        if cl.fact_class in (FactClass.FORECAST, FactClass.OPINION) and cl.materiality == "high" and cl.confidence > 0.8:
            add("high", "UNSUPPORTED_CERTAINTY", f"claim {cl.claim_id} is {cl.fact_class.value} but asserted with high certainty")
    # weak single-source thesis
    material_sources = {cl.source_id for cl in claims if cl.materiality == "high"}
    if len(material_sources) <= 1 and claims:
        add("high", "SINGLE_SOURCE_RISK", "material conclusions rest on one source")
    # stale evidence
    if any(s.quality == SourceQuality.STALE for s in sources):
        add("medium", "STALE_EVIDENCE", "one or more sources are stale")
    # missing downside scenario
    if not any((sc.get("name", "").lower().find("down") >= 0 or sc.get("name", "").lower().find("bear") >= 0) for sc in scenarios):
        add("high", "MISSING_DOWNSIDE", "no downside/bear scenario present")

    critical = [f for f in findings if f["severity"] == "critical"]
    disposition = "REVISION_REQUIRED" if critical else ("REVIEW_READY" if not any(f["severity"] == "high" for f in findings) else "REVISION_REQUIRED")
    return {
        "challenger_role": challenger_role,
        "findings": findings,
        "critical_count": len(critical),
        "unresolved_objections": [f for f in findings if f["severity"] in ("critical", "high")],
        "recommended_disposition": disposition,
    }
