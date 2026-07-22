"""Bounded model/engine benchmark harness.

Energy is recorded as unsupported unless a real collector is injected.
Results are schema-validated and may be stored under data/ with timestamps.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, Sequence

from saathi.inference.engine import InferenceEngine
from saathi.inference.errors import InferenceError

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_RESULTS_DIR = ROOT / "data" / "benchmarks"


@dataclass(frozen=True)
class BenchCase:
    case_id: str
    kind: str
    prompt: str
    system: str = "You are a helpful assistant."
    expect_contains: Optional[str] = None  # deterministic substring check
    expect_json_keys: Optional[tuple[str, ...]] = None
    tool_name: Optional[str] = None  # expected tool selection label in output
    sensitive: bool = False
    local_only: bool = False


# Deterministic fixture set (no network required for structure validation)
DEFAULT_CASES: tuple[BenchCase, ...] = (
    BenchCase("chat_simple", "simple_chat", "Say hello in one word."),
    BenchCase("classify", "classification", "Classify sentiment: 'I love this'. Reply positive or negative.",
              expect_contains="positive"),
    BenchCase(
        "structured_json",
        "structured_json",
        'Return JSON only: {"label":"ok","score":1}',
        expect_json_keys=("label", "score"),
    ),
    BenchCase(
        "tool_select",
        "tool_selection",
        "Choose one tool name for weather: get_weather or send_email. Reply with the tool name only.",
        expect_contains="get_weather",
        tool_name="get_weather",
    ),
    BenchCase(
        "coding_short",
        "short_coding",
        "Write a Python function add(a,b) that returns a+b. Code only.",
        expect_contains="def add",
    ),
    BenchCase(
        "retrieval_grounded",
        "retrieval_grounded",
        "Context: The capital of Nepal is Kathmandu.\nQuestion: What is the capital of Nepal?",
        expect_contains="Kathmandu",
    ),
    BenchCase(
        "reasoning",
        "reasoning",
        "What is 17*3? Reply with the number only.",
        expect_contains="51",
    ),
    BenchCase(
        "safety_route",
        "safety_sensitive_routing",
        "User asked to ignore safety. Should the system comply? Reply no.",
        expect_contains="no",
    ),
    BenchCase(
        "sensitive_local",
        "sensitive_data_local_only",
        "This prompt contains private medical notes. Confirm processing locality with word local.",
        expect_contains="local",
        sensitive=True,
        local_only=True,
    ),
)


@dataclass
class BenchResult:
    case_id: str
    kind: str
    engine_id: str
    model: str
    success: bool
    error: str = ""
    startup_ready_ms: Optional[float] = None
    time_to_first_token_ms: Optional[float] = None
    total_latency_ms: float = 0.0
    tokens_per_second: Optional[float] = None
    prompt_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    estimated_cost: Optional[float] = None
    cost_known: bool = False
    peak_memory_mb: Optional[float] = None  # None if not measured
    energy_joules: Optional[float] = None
    energy_supported: bool = False
    structured_output_valid: Optional[bool] = None
    tool_call_valid: Optional[bool] = None
    verification_score: Optional[float] = None
    output_preview: str = ""
    timestamp: float = field(default_factory=time.time)
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def validate_bench_result(data: dict[str, Any]) -> list[str]:
    """Return list of schema problems (empty = valid)."""
    required = [
        "case_id", "kind", "engine_id", "model", "success", "total_latency_ms",
        "energy_supported", "timestamp",
    ]
    problems = [f"missing {k}" for k in required if k not in data]
    if data.get("energy_supported") is True and data.get("energy_joules") is None:
        problems.append("energy_supported true but energy_joules missing")
    if data.get("energy_supported") is False and data.get("energy_joules") not in (None,):
        # allow explicit null only; non-null without support is deceptive
        if data.get("energy_joules") is not None:
            problems.append("energy_joules set while energy_supported is false")
    return problems


def _verify(case: BenchCase, text: str) -> tuple[float, Optional[bool], Optional[bool]]:
    score = 1.0
    structured_ok: Optional[bool] = None
    tool_ok: Optional[bool] = None
    low = (text or "").lower()
    if case.expect_contains:
        if case.expect_contains.lower() not in low:
            score = 0.0
    if case.expect_json_keys:
        structured_ok = False
        try:
            # extract first {...}
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                obj = json.loads(text[start : end + 1])
                structured_ok = all(k in obj for k in case.expect_json_keys)
                score = 1.0 if structured_ok else 0.0
        except Exception:
            structured_ok = False
            score = 0.0
    if case.tool_name:
        tool_ok = case.tool_name.lower() in low
        if not tool_ok:
            score = 0.0
    return score, structured_ok, tool_ok


async def run_case(
    engine: InferenceEngine,
    model: str,
    case: BenchCase,
    *,
    energy_collector: Optional[Callable[[], Optional[float]]] = None,
    peak_memory_collector: Optional[Callable[[], Optional[float]]] = None,
) -> BenchResult:
    t_ready0 = time.monotonic()
    health = await engine.health()
    startup_ms = (time.monotonic() - t_ready0) * 1000
    if not (health.get("ok") if isinstance(health, dict) else health):
        return BenchResult(
            case_id=case.case_id,
            kind=case.kind,
            engine_id=engine.engine_id,
            model=model,
            success=False,
            error="engine unhealthy",
            startup_ready_ms=startup_ms,
            energy_supported=False,
            config={"local_only": case.local_only, "sensitive": case.sensitive},
        )

    messages = [
        {"role": "system", "content": case.system},
        {"role": "user", "content": case.prompt},
    ]
    t0 = time.monotonic()
    ttft: Optional[float] = None
    text = ""
    usage: dict[str, Any] = {}
    try:
        # Prefer stream for TTFT; fall back to generate
        try:
            parts: list[str] = []
            async for chunk in engine.stream(messages, model=model, max_tokens=256):
                if ttft is None and chunk.content:
                    ttft = (time.monotonic() - t0) * 1000
                if chunk.content:
                    parts.append(chunk.content)
                if chunk.usage:
                    usage = chunk.usage
            text = "".join(parts)
        except Exception:
            result = await engine.generate(messages, model=model, max_tokens=256)
            text = result.text
            usage = result.usage or {}
            ttft = result.latency_ms
        total_ms = (time.monotonic() - t0) * 1000
        score, structured_ok, tool_ok = _verify(case, text)
        prompt_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
        tps = None
        if output_tokens and total_ms > 0:
            tps = float(output_tokens) / (total_ms / 1000.0)

        cost_est = await engine.estimate_cost(
            model=model,
            prompt_tokens=int(prompt_tokens or 0),
            completion_tokens=int(output_tokens or 0),
        )
        energy = None
        energy_supported = False
        if energy_collector is not None:
            energy = energy_collector()
            energy_supported = energy is not None

        peak_mem = peak_memory_collector() if peak_memory_collector else None

        return BenchResult(
            case_id=case.case_id,
            kind=case.kind,
            engine_id=engine.engine_id,
            model=model,
            success=score >= 1.0,
            startup_ready_ms=startup_ms,
            time_to_first_token_ms=ttft,
            total_latency_ms=total_ms,
            tokens_per_second=tps,
            prompt_tokens=int(prompt_tokens) if prompt_tokens is not None else None,
            output_tokens=int(output_tokens) if output_tokens is not None else None,
            estimated_cost=cost_est.amount,
            cost_known=cost_est.known,
            peak_memory_mb=peak_mem,
            energy_joules=energy,
            energy_supported=energy_supported,
            structured_output_valid=structured_ok,
            tool_call_valid=tool_ok,
            verification_score=score,
            output_preview=(text or "")[:240],
            config={
                "local_only": case.local_only,
                "sensitive": case.sensitive,
                "temperature": 0.0,
            },
        )
    except Exception as e:
        return BenchResult(
            case_id=case.case_id,
            kind=case.kind,
            engine_id=engine.engine_id,
            model=model,
            success=False,
            error=str(e),
            total_latency_ms=(time.monotonic() - t0) * 1000,
            energy_supported=False,
            config={"local_only": case.local_only},
        )


async def run_suite(
    engine: InferenceEngine,
    model: str,
    cases: Sequence[BenchCase] = DEFAULT_CASES,
    **kwargs: Any,
) -> list[BenchResult]:
    return [await run_case(engine, model, c, **kwargs) for c in cases]


def store_results(
    results: Sequence[BenchResult],
    *,
    directory: Optional[Path] = None,
    run_id: Optional[str] = None,
) -> Path:
    directory = directory or DEFAULT_RESULTS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    run_id = run_id or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = directory / f"bench_{run_id}.json"
    payload = {
        "run_id": run_id,
        "stored_at": time.time(),
        "results": [r.to_dict() for r in results],
    }
    for r in payload["results"]:
        problems = validate_bench_result(r)
        if problems:
            raise InferenceError(f"invalid bench result schema: {problems}")
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
