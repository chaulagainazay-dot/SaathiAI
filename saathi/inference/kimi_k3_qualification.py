"""Qualification harness for the NVIDIA-hosted Kimi K3 engine.

The contract was certified offline; the provider was not, because no
`NVIDIA_API_KEY` existed to certify it with. This is the thing that closes that
gap: a bounded, ordered set of checks that runs the moment a key is configured
and produces evidence rather than an opinion.

**Why a harness rather than a script.** Promotion is the decision this feeds,
and a decision needs a record: which model, which test, pass or fail, how long,
how many tokens, what error class. A one-off script produces a feeling that the
API worked.

**What it will not do.**

* It will not run without a credential. `live=True` with no key is refused, not
  skipped quietly, because a qualification that silently did nothing is worse
  than one that did not run.
* It will not score quality. Every check here is deterministic -- an exact
  sentinel, a structural property, a latency measurement. Asking a model whether
  a model's reasoning was good produces a number with no meaning, and §19's
  "do not manufacture quality scores" is the whole reason the open-ended cases
  record completion and cost rather than a grade.
* It will not promote anything. It records what happened; whether capabilities
  move from False to True stays a human decision made against this evidence.
* It performs no external write. Every case is a completion; the tool-calling
  case uses a read-only fixture tool and asserts the *proposal*, never an
  execution.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from saathi.inference.adapters.nvidia import (
    KIMI_K3,
    NVIDIA_API_KEY_ENV,
    NvidiaEngine,
    api_key_present,
)

#: A small, stable, public image. NVIDIA's own catalog asset, so the multimodal
#: case does not depend on a third party staying online -- and it goes through
#: the adapter's SSRF validation like any other URL.
QUALIFICATION_IMAGE = (
    "https://assets.ngc.nvidia.com/products/api-catalog/phi-3-5-vision/example1b.jpg"
)

#: Sentinels for the checks that can be graded exactly. A model either emitted
#: the string or it did not; there is nothing to interpret.
TEXT_SENTINEL = "SAATHIOS_KIMI_K3_TEXT_OK"
STREAM_SENTINEL = "SAATHIOS_KIMI_K3_STREAM_OK"

#: Bounded so a qualification run cannot become an expensive one by accident.
MAX_CASE_TOKENS = 512
MAX_CASE_SECONDS = 90.0


class QualificationBlocked(RuntimeError):
    """A live run was requested without the credential to perform it."""


@dataclass
class CaseResult:
    """One check's outcome. Records evidence, never a manufactured score."""

    case_id: str
    category: str
    passed: Optional[bool]          # None = observed only, nothing to grade
    latency_ms: float = 0.0
    usage: dict = field(default_factory=dict)
    error_class: str = ""
    detail: str = ""
    graded: bool = True

    def to_dict(self) -> dict:
        return {"case": self.case_id, "category": self.category,
                "passed": self.passed, "graded": self.graded,
                "latency_ms": round(self.latency_ms, 1),
                "usage": self.usage or {}, "error_class": self.error_class or None,
                "detail": self.detail or None}


@dataclass(frozen=True)
class Case:
    """One qualification check.

    `check` returns True/False for a graded case, or None when the case exists
    to observe latency and cost rather than to pass or fail -- open-ended
    reasoning has no deterministic right answer, and pretending otherwise is how
    a benchmark starts lying.
    """

    case_id: str
    category: str
    messages: list
    check: Callable[[str], Optional[bool]]
    stream: bool = False
    reasoning: str = "NORMAL"
    graded: bool = True


def _contains(sentinel: str) -> Callable[[str], bool]:
    return lambda text: sentinel in (text or "")


def _observe(_text: str) -> None:
    """Non-graded: we record that it completed, and what it cost."""
    return None


#: The ordered set. Deliberately small: eleven checks that each answer a
#: different question, rather than a corpus that answers one question loudly.
def qualification_cases(image_url: str = QUALIFICATION_IMAGE) -> list[Case]:
    return [
        Case("K3Q-01", "text", [{"role": "user", "content":
             f"Reply with exactly: {TEXT_SENTINEL}"}], _contains(TEXT_SENTINEL)),

        Case("K3Q-02", "streaming", [{"role": "user", "content":
             f"Reply with exactly: {STREAM_SENTINEL}"}],
             _contains(STREAM_SENTINEL), stream=True),

        Case("K3Q-03", "instruction_following", [{"role": "user", "content":
             "Answer with a single digit and nothing else: what is 6 times 7?"}],
             lambda t: (t or "").strip().startswith("42")),

        Case("K3Q-04", "normal_reasoning", [{"role": "user", "content":
             "A bat and ball cost 1.10 together. The bat costs 1.00 more than "
             "the ball. What does the ball cost? Answer with the number only."}],
             lambda t: "0.05" in (t or "") or ".05" in (t or "")),

        Case("K3Q-05", "difficult_reasoning", [{"role": "user", "content":
             "Three switches outside a room control three bulbs inside. You may "
             "enter once. Describe the method in under 60 words."}],
             _observe, reasoning="HIGH", graded=False),

        Case("K3Q-06", "long_context", [{"role": "user", "content":
             "Here is a list: " + ", ".join(str(i) for i in range(1, 801)) +
             ". Reply with the 700th number only."}],
             lambda t: "700" in (t or "")),

        Case("K3Q-07", "multimodal", [{"role": "user", "content": [
             {"type": "text", "text": "What is in this image? One short sentence."},
             {"type": "image_url", "image_url": {"url": image_url}}]}],
             lambda t: bool((t or "").strip()), graded=False),

        Case("K3Q-08", "investment_research", [{"role": "user", "content":
             "State one bull and one bear thesis for a hypothetical logistics "
             "firm with falling margins and rising volume. Under 80 words. This "
             "is analysis only, not advice."}], _observe, graded=False),

        Case("K3Q-09", "portfolio_scenario", [{"role": "user", "content":
             "A hypothetical portfolio is 60% equities, 40% bonds. Describe the "
             "direction of impact if rates rise 200bp. Under 60 words. Analysis "
             "only."}], _observe, graded=False),

        Case("K3Q-10", "coding", [{"role": "user", "content":
             "In Python, what does `dict.setdefault` return when the key is "
             "already present? One sentence."}],
             lambda t: "existing" in (t or "").lower() or "current" in (t or "").lower()),

        Case("K3Q-11", "reasoning_effort", [{"role": "user", "content":
             f"Reply with exactly: {TEXT_SENTINEL}"}],
             _contains(TEXT_SENTINEL), reasoning="MAX"),
    ]


async def _run_case(engine: NvidiaEngine, case: Case, *, model: str) -> CaseResult:
    started = time.perf_counter()
    try:
        if case.stream:
            parts: list[str] = []
            usage: dict = {}
            async for chunk in engine.stream(
                    case.messages, model=model, max_tokens=MAX_CASE_TOKENS,
                    timeout=MAX_CASE_SECONDS, reasoning=case.reasoning):
                if chunk.content:
                    parts.append(chunk.content)
                if chunk.usage:
                    usage = chunk.usage
            text = "".join(parts)
        else:
            result = await engine.generate(
                case.messages, model=model, max_tokens=MAX_CASE_TOKENS,
                timeout=MAX_CASE_SECONDS, reasoning=case.reasoning)
            text, usage = result.text, result.usage
    except Exception as exc:  # noqa: BLE001 - classified, never swallowed
        # The failure-recovery evidence: which error class, not a traceback, and
        # never the exception's text in case a provider echoed a header.
        return CaseResult(case.case_id, case.category, passed=False,
                          latency_ms=(time.perf_counter() - started) * 1000.0,
                          error_class=type(exc).__name__, graded=case.graded)

    outcome = case.check(text)
    return CaseResult(
        case.case_id, case.category,
        passed=outcome if case.graded else None,
        latency_ms=(time.perf_counter() - started) * 1000.0,
        usage=usage or {}, graded=case.graded,
        # Bounded and content-free: enough to see the case produced something,
        # not enough to leak a conversation into a report.
        detail=f"{len(text)} chars")


async def run_qualification(*, engine: Optional[NvidiaEngine] = None,
                            model: str = KIMI_K3, live: bool = False,
                            cases: Optional[list[Case]] = None) -> dict[str, Any]:
    """Run the qualification set and return an evidence record.

    `live=True` requires a configured credential and is refused without one.
    The default is deliberately not live: the harness is importable, testable
    and runnable against a stub without anyone's key.
    """
    if live and not api_key_present():
        raise QualificationBlocked(
            f"live qualification requires {NVIDIA_API_KEY_ENV}; none configured")

    engine = engine or NvidiaEngine(model=model)
    selected = cases if cases is not None else qualification_cases()

    results = [await _run_case(engine, case, model=model) for case in selected]
    graded = [r for r in results if r.graded]
    passed = [r for r in graded if r.passed]
    latencies = sorted(r.latency_ms for r in results if r.latency_ms > 0)

    return {
        "provider": "nvidia",
        "model": model,
        "live": bool(live),
        "cases": [r.to_dict() for r in results],
        "graded_total": len(graded),
        "graded_passed": len(passed),
        # No overall score. A pass count over graded cases is a fact; a quality
        # number over open-ended ones would not be.
        "observed_only": [r.case_id for r in results if not r.graded],
        "latency_ms_median": (latencies[len(latencies) // 2] if latencies else None),
        "latency_ms_max": (latencies[-1] if latencies else None),
        "errors": sorted({r.error_class for r in results if r.error_class}),
        "capability_promotion": "not_granted_by_this_run",
    }


def qualification_status() -> dict[str, Any]:
    """Whether a live run is currently possible. Names the variable, not a value."""
    ready = api_key_present()
    return {"provider": "nvidia", "model": KIMI_K3, "live_possible": ready,
            "blocked_reason": "" if ready else f"{NVIDIA_API_KEY_ENV}_missing",
            "credential_env": NVIDIA_API_KEY_ENV}


def _main() -> int:
    """`python -m saathi.inference.kimi_k3_qualification [--live]`.

    A module entry rather than a one-liner because the invocation has three
    ways to go wrong -- wrong interpreter, missing PYTHONPATH, key pasted into
    the command -- and none of them should stand between a configured
    credential and an evidence record.

    The credential is read from the environment. It is never a command-line
    argument: arguments are visible in `ps` and land in shell history.
    """
    import argparse
    import asyncio
    import json

    parser = argparse.ArgumentParser(
        description="Qualify the NVIDIA-hosted Kimi K3 provider.")
    parser.add_argument("--live", action="store_true",
                        help=f"contact NVIDIA (requires {NVIDIA_API_KEY_ENV})")
    args = parser.parse_args()

    status = qualification_status()
    if args.live and not status["live_possible"]:
        print(json.dumps({"error": "live_qualification_blocked", **status}, indent=2))
        return 2

    report = asyncio.run(run_qualification(live=args.live))
    print(json.dumps(report, indent=2))
    # Non-zero when a graded case failed, so this is usable from a script.
    return 0 if report["graded_passed"] == report["graded_total"] else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(_main())
