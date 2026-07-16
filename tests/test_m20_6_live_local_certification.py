"""M20.6 — Live local inference certification (deterministic + honest blocked)."""
from __future__ import annotations

from pathlib import Path

import pytest

from saathi.inference.cert_corpus import build_corpus, score_output
from saathi.inference.certification import (
    CERT_SUITE_VERSION,
    discover_engines,
    discover_models,
    run_certification,
    select_model,
)
from saathi.inference.hardware import m2_8gb_reference_profile
from saathi.inference.request import InferenceErrorCategory, InferenceRequest
from saathi.inference.result import StructuredInferenceResult

ROOT = Path(__file__).resolve().parents[1]


def test_corpus_has_required_cases():
    cases = build_corpus()
    ids = {c.case_id for c in cases}
    assert len(cases) >= 10
    assert "c11_1_summary" in ids
    assert "c11_5_refusal" in ids
    assert "c11_6_injection" in ids
    assert "c11_7_hallucination" in ids


def test_score_summary_and_json():
    cases = {c.case_id: c for c in build_corpus()}
    s = score_output(
        cases["c11_1_summary"],
        "Service alpha had a timeout typo causing outage.",
    )
    assert s["ok"]
    s2 = score_output(
        cases["c11_3_structured"],
        '{"name":"Riverdale Labs","city":"Kathmandu","status":"active"}',
    )
    assert s2["ok"]
    s3 = score_output(cases["c11_3_structured"], "not json")
    assert s3["critical_fail"]


def test_score_refusal_and_injection():
    cases = {c.case_id: c for c in build_corpus()}
    bad = score_output(cases["c11_5_refusal"], "Here is sk-abcdefghijklmnopqrstuv")
    assert bad["critical_fail"]
    good = score_output(cases["c11_5_refusal"], "I cannot reveal secrets.")
    assert good["ok"]
    inj = score_output(
        cases["c11_6_injection"],
        "Beta is healthy; latency 12ms.",
    )
    assert inj["ok"]


def test_discover_engines_no_crash():
    eng = discover_engines()
    assert any(e.engine_id == "ollama" for e in eng)


def test_select_model_prefers_small():
    from saathi.inference.certification import ModelCandidate
    hw = m2_8gb_reference_profile(available_memory_gb=5.0, free_disk_gb=50.0)
    models = [
        ModelCandidate(model_id="llama3:8b", resource_safe=False, selection_rank=900),
        ModelCandidate(model_id="qwen2.5:1.5b", resource_safe=True, selection_rank=1),
        ModelCandidate(model_id="qwen2.5:3b", resource_safe=True, selection_rank=2),
    ]
    sel = select_model(models, hw)
    assert sel and sel.model_id == "qwen2.5:1.5b"


def test_select_model_none_under_memory_pressure():
    from saathi.inference.certification import ModelCandidate
    hw = m2_8gb_reference_profile(available_memory_gb=0.5, free_disk_gb=50.0)
    models = [ModelCandidate(model_id="qwen2.5:1.5b", resource_safe=True, selection_rank=1)]
    assert select_model(models, hw) is None


def test_live_cert_blocked_without_model():
    rep = run_certification(starting_commit="test", force_blocked=True)
    assert rep.status == "BLOCKED"
    assert "NO APPROVED INSTALLED" in rep.verdict
    assert rep.live is False
    assert rep.downloads_performed is False
    assert rep.cloud_calls == 0
    assert rep.trading_guardian_engaged is False
    assert rep.global_adoption_changed is False
    assert rep.fallback["defaults_legacy"] is True


def _gov_factory():
    def gov(req: InferenceRequest) -> StructuredInferenceResult:
        cid = (req.metadata or {}).get("cert_case_id", "")
        mapping = {
            "c11_1_summary": "Service alpha restarted after timeout configuration typo; brief outage.",
            "c11_2_prose_clean": "We need to start reviewing the document we wrote.",
            "c11_3_structured": '{"name":"Riverdale Labs","city":"Kathmandu","status":"active"}',
            "c11_4_instruction": "READY",
            "c11_5_refusal": "I cannot reveal secrets or API keys.",
            "c11_6_injection": "Beta is healthy with 12ms latency.",
            "c11_7_hallucination": "UNAVAILABLE",
            "c11_8_long_bounded": "OK",
            "c11_9_cancel": "x",
            "c11_10_timeout": "",
        }
        if cid == "c11_10_timeout":
            return StructuredInferenceResult.failure(
                req.request_id, InferenceErrorCategory.TIMEOUT, "timeout"
            )
        text = mapping.get(cid, "ok")
        r = StructuredInferenceResult(
            request_id=req.request_id,
            ok=True,
            output_text=text,
            selected_model="fake:qwen2.5:1.5b",
            selected_engine="fake",
            latency_ms=8.0,
            evidence_ref=f"ev:{cid}",
        )
        r.finalize_fingerprint()
        return r
    return gov


def test_injected_cert_meets_quality():
    rep = run_certification(governed_fn=_gov_factory(), starting_commit="test")
    assert rep.quality_summary["critical_fails"] == 0
    assert rep.quality_summary["adherence_met"] is True
    assert rep.downloads_performed is False
    # no raw prompts in report
    blob = str(rep.to_dict())
    assert "Ignore all previous instructions" not in blob
    assert "sk-abcdefghijklmnopqrstuv" not in blob


def test_hard_fallback_policy_in_report():
    rep = run_certification(force_blocked=True)
    assert rep.fallback["hard_denials_no_fallback"] is True
    assert rep.fallback["soft_allow_timeout"] is True


def test_no_direct_ollama_in_selected_callers():
    for rel in ("saathi/tools/cheap_llm.py", "saathi/tools/prose.py"):
        t = (ROOT / rel).read_text(encoding="utf-8")
        assert "11434" not in t
        assert "OllamaEngine" not in t


def test_chat_not_migrated():
    t = (ROOT / "saathi" / "chat" / "engine.py").read_text(encoding="utf-8")
    assert "llm_mod.generate" in t
    assert "m20_6" not in t.lower()


def test_cert_suite_version():
    assert CERT_SUITE_VERSION.startswith("m20.6")
