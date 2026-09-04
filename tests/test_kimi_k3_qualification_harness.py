"""The Kimi K3 qualification harness, certified offline.

Live qualification is blocked without a credential, and that is not something
this file can fix. What it can establish is that the harness is correct *before*
a key exists -- so when one appears, the run that follows is trustworthy rather
than the first time anybody exercised the code that grades it.

The properties that matter here are mostly refusals: it will not run live
without a credential, it will not report a pass it did not observe, it will not
manufacture a quality score for an open-ended answer, and it will not leak a
credential or a conversation into its report.

Every test drives a stub engine. Nothing contacts NVIDIA.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from saathi.inference.adapters.nvidia import KIMI_K3, NVIDIA_API_KEY_ENV
from saathi.inference.engine import GenerateResult, StreamChunk
from saathi.inference.errors import EngineUnhealthyError
from saathi.inference.kimi_k3_qualification import (
    MAX_CASE_SECONDS,
    MAX_CASE_TOKENS,
    QUALIFICATION_IMAGE,
    QualificationBlocked,
    STREAM_SENTINEL,
    TEXT_SENTINEL,
    qualification_cases,
    qualification_status,
    run_qualification,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import httpx

    def _boom(*a, **k):
        raise AssertionError("the harness attempted a real NVIDIA request")

    for verb in ("post", "get", "stream", "request"):
        monkeypatch.setattr(httpx, verb, _boom, raising=False)


class _StubEngine:
    """Answers every case correctly. The control for the graded set."""

    def __init__(self, *, answers=None, fail_with=None):
        self.answers = answers or {}
        self.fail_with = fail_with
        self.calls = []

    def _answer(self, messages) -> str:
        text = json.dumps(messages)
        if TEXT_SENTINEL in text:
            return TEXT_SENTINEL
        if STREAM_SENTINEL in text:
            return STREAM_SENTINEL
        if "6 times 7" in text:
            return "42"
        if "bat and ball" in text:
            return "0.05"
        if "700th number" in text:
            return "700"
        if "setdefault" in text:
            return "It returns the existing value for that key."
        return "a plausible open-ended answer"

    async def generate(self, messages, *, model, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs, "stream": False})
        if self.fail_with:
            raise self.fail_with
        return GenerateResult(text=self._answer(messages), model=model,
                              engine_id="stub", usage={"total_tokens": 11})

    async def stream(self, messages, *, model, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs, "stream": True})
        if self.fail_with:
            raise self.fail_with
        for piece in (self._answer(messages), ""):
            if piece:
                yield StreamChunk(content=piece)
        yield StreamChunk(finish_reason="stop", usage={"total_tokens": 7})


# ── it refuses to run live without a credential ────────────────────────────

def test_live_qualification_is_refused_without_a_key(monkeypatch):
    """Refused, not skipped. A qualification that quietly did nothing is worse
    than one that did not run."""
    monkeypatch.delenv(NVIDIA_API_KEY_ENV, raising=False)
    with pytest.raises(QualificationBlocked):
        asyncio.run(run_qualification(engine=_StubEngine(), live=True))


def test_the_status_probe_names_the_variable_not_a_value(monkeypatch):
    monkeypatch.delenv(NVIDIA_API_KEY_ENV, raising=False)
    status = qualification_status()
    assert status["live_possible"] is False
    assert status["blocked_reason"] == f"{NVIDIA_API_KEY_ENV}_missing"
    assert status["credential_env"] == NVIDIA_API_KEY_ENV


def test_the_status_probe_reports_ready_when_a_key_exists(monkeypatch):
    monkeypatch.setenv(NVIDIA_API_KEY_ENV, "TEST-FIXTURE-NOT-A-CREDENTIAL")
    status = qualification_status()
    assert status["live_possible"] is True and status["blocked_reason"] == ""
    assert "TEST-FIXTURE" not in json.dumps(status)


def test_a_non_live_run_needs_no_credential(monkeypatch):
    """The harness must be exercisable without anyone's key, or it is first
    tested during the run that matters."""
    monkeypatch.delenv(NVIDIA_API_KEY_ENV, raising=False)
    report = asyncio.run(run_qualification(engine=_StubEngine()))
    assert report["live"] is False and report["graded_total"] > 0


# ── it grades honestly ─────────────────────────────────────────────────────

def test_a_correct_engine_passes_every_graded_case():
    """The positive control. Without it, every failure below could be the
    harness rejecting everything."""
    report = asyncio.run(run_qualification(engine=_StubEngine()))
    assert report["graded_passed"] == report["graded_total"]
    assert report["errors"] == []


def test_a_wrong_answer_is_recorded_as_a_failure():
    class _Wrong(_StubEngine):
        def _answer(self, messages):
            return "definitely not the sentinel"

    report = asyncio.run(run_qualification(engine=_Wrong()))
    assert report["graded_passed"] == 0
    assert report["graded_total"] > 0


def test_open_ended_cases_are_observed_not_scored():
    """§19: do not manufacture quality scores. There is no right answer to
    'describe the bulb puzzle', so those cases record cost and completion."""
    report = asyncio.run(run_qualification(engine=_StubEngine()))
    observed = set(report["observed_only"])
    assert {"K3Q-05", "K3Q-07", "K3Q-08", "K3Q-09"} <= observed
    for case in report["cases"]:
        if case["case"] in observed:
            assert case["passed"] is None, "an ungradeable case must not claim a pass"
            assert case["graded"] is False


def test_the_report_carries_no_overall_quality_score():
    """Checked by key, not by substring: `graded` is a boolean saying whether a
    case *can* be graded, and a text search for "grade" flags it -- the field
    that exists precisely to stop ungradeable cases claiming a pass."""
    report = asyncio.run(run_qualification(engine=_StubEngine()))

    def score_like(keys):
        return {k for k in keys
                if k.lower() in {"score", "rating", "quality", "grade",
                                 "overall_score", "quality_score"}}

    assert score_like(report) == set()
    for case in report["cases"]:
        assert score_like(case) == set()
        # `graded` is a flag; a score would be a number.
        assert isinstance(case["graded"], bool)
    # A pass count over graded cases is a fact. Nothing aggregates the
    # ungradeable ones into a number.
    assert isinstance(report["graded_passed"], int)
    assert report["graded_passed"] <= report["graded_total"]


def test_the_run_grants_no_capability_promotion():
    """Evidence for a decision, not the decision."""
    report = asyncio.run(run_qualification(engine=_StubEngine()))
    assert report["capability_promotion"] == "not_granted_by_this_run"


# ── failure recovery is evidence, not a crash ──────────────────────────────

def test_a_provider_failure_is_recorded_by_class_not_raised():
    report = asyncio.run(run_qualification(
        engine=_StubEngine(fail_with=EngineUnhealthyError("nvidia rate limited"))))
    assert report["errors"] == ["EngineUnhealthyError"]
    assert report["graded_passed"] == 0
    assert all(c["passed"] is False for c in report["cases"] if c["graded"])


def test_a_failure_detail_carries_no_provider_text():
    """A provider error can echo the request that failed, headers included."""
    report = asyncio.run(run_qualification(
        engine=_StubEngine(fail_with=EngineUnhealthyError(
            "401 for key LEAKED-CREDENTIAL-MARKER"))))
    # Deliberately not shaped like a real NVIDIA key: using the vendor's
    # `nvapi-` prefix would make this line trip every secret scanner that looks
    # for one, for a value that is not a secret.
    assert "LEAKED-CREDENTIAL-MARKER" not in json.dumps(report)


def test_case_details_do_not_carry_conversation_content():
    """A qualification report is operational evidence, not a transcript."""
    report = asyncio.run(run_qualification(engine=_StubEngine()))
    blob = json.dumps(report)
    assert TEXT_SENTINEL not in blob, "model output leaked into the report"
    assert "bat and ball" not in blob, "prompt content leaked into the report"


# ── the cases themselves ───────────────────────────────────────────────────

def test_every_required_category_is_covered():
    """§19's list, so a category cannot be quietly dropped."""
    categories = {c.category for c in qualification_cases()}
    for required in ("text", "streaming", "normal_reasoning",
                     "difficult_reasoning", "long_context", "multimodal",
                     "investment_research", "portfolio_scenario", "coding",
                     "instruction_following", "reasoning_effort"):
        assert required in categories, required


def test_case_ids_are_unique():
    cases = qualification_cases()
    assert len({c.case_id for c in cases}) == len(cases)


def test_the_multimodal_case_uses_a_public_image_and_is_validated():
    """It goes through the adapter's SSRF validation like any other URL."""
    from saathi.inference.adapters.nvidia import validate_image_url

    assert QUALIFICATION_IMAGE.startswith("https://")
    ok, reason = validate_image_url(QUALIFICATION_IMAGE,
                                    resolver=lambda h: ["93.184.216.34"])
    assert ok is True and reason == "ok"


def test_the_multimodal_image_would_be_refused_if_it_resolved_internally():
    """The validation is real, not decorative."""
    from saathi.inference.adapters.nvidia import validate_image_url

    ok, reason = validate_image_url(QUALIFICATION_IMAGE,
                                    resolver=lambda h: ["169.254.169.254"])
    assert ok is False and reason == "blocked_metadata"


def test_cases_are_bounded_in_cost_and_time():
    """A qualification run must not become an expensive one by accident."""
    assert 0 < MAX_CASE_TOKENS <= 1024
    assert 0 < MAX_CASE_SECONDS <= 120

    engine = _StubEngine()
    asyncio.run(run_qualification(engine=engine))
    for call in engine.calls:
        assert call["kwargs"]["max_tokens"] == MAX_CASE_TOKENS
        assert call["kwargs"]["timeout"] == MAX_CASE_SECONDS


def test_the_reasoning_case_actually_requests_max_effort():
    engine = _StubEngine()
    asyncio.run(run_qualification(engine=engine))
    efforts = {c["kwargs"].get("reasoning") for c in engine.calls}
    assert "MAX" in efforts and "NORMAL" in efforts


def test_the_streaming_case_uses_the_streaming_path():
    engine = _StubEngine()
    asyncio.run(run_qualification(engine=engine))
    assert any(c["stream"] for c in engine.calls)
    assert any(not c["stream"] for c in engine.calls)


# ── the harness performs no external write ─────────────────────────────────

def test_the_harness_cannot_reach_execution_machinery():
    """Qualification exercises a model. It must not be able to act."""
    import ast
    import pathlib

    tree = ast.parse(
        pathlib.Path("saathi/inference/kimi_k3_qualification.py").read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    for forbidden in ("saathi.execution.gateway", "saathi.execution.egress",
                      "saathi.agent_runtime.gateway_exec", "saathi.platform.tg",
                      "saathi.execution.writers"):
        assert not any(m.startswith(forbidden) for m in imported), forbidden


def test_no_qualification_case_proposes_a_write():
    """Every case is a completion. None asks the model to send, post or trade."""
    blob = json.dumps([c.messages for c in qualification_cases()]).lower()
    for forbidden in ("send an email", "post to", "execute a trade", "buy ",
                      "sell ", "transfer "):
        assert forbidden not in blob, forbidden


def test_the_financial_cases_are_marked_analysis_only():
    cases = {c.case_id: c for c in qualification_cases()}
    for case_id in ("K3Q-08", "K3Q-09"):
        text = json.dumps(cases[case_id].messages).lower()
        assert "analysis only" in text or "not advice" in text
