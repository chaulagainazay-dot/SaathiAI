#!/usr/bin/env python3
"""Write deterministic offline workflow and provider-comparison artifacts."""
from __future__ import annotations

import json
import time
from pathlib import Path

from saathi.evaluation.collaboration import evaluate_collaboration
from saathi.evaluation.workflows import run_workflow_evaluations
from saathi.inference.adapters.kimi import KIMI_PRICING
from saathi.inference.priority_policy import DEFAULT_CLOUD_BUDGET

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "evaluation"


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    results = run_workflow_evaluations()
    collaboration = [evaluate_collaboration(result.trace).to_dict() for result in results]
    workflow_payload = {
        "schema": "saathios.workflow_evaluation.v1",
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "deterministic": True,
        "offline": True,
        "results": [result.to_dict() for result in results],
        "collaboration_reviews": collaboration,
    }
    (ARTIFACTS / "workflow-results.json").write_text(
        json.dumps(workflow_payload, indent=2), encoding="utf-8"
    )
    provider_payload = {
        "schema": "saathios.provider_comparison.v1",
        "recorded_at": workflow_payload["recorded_at"],
        "budget_policy": DEFAULT_CLOUD_BUDGET.to_dict(),
        "providers": [
            {
                "provider": "ollama",
                "model": "qwen2.5:1.5b",
                "execution": "local benchmark artifact",
                "cost_usd": "0.00",
                "decision": "KEEP_DEFAULT",
            },
            {
                "provider": "kimi",
                "model": "kimi-k2.7-code",
                "execution": "deterministic adapter contract only; no credential/no live call",
                "pricing_usd_per_million": KIMI_PRICING["kimi-k2.7-code"],
                "task_success": None,
                "tool_discipline": None,
                "decision": "BENCHMARK_DEFERRED_NO_CREDENTIAL",
            },
            {
                "provider": "kimi",
                "model": "kimi-k3",
                "execution": "not called; expensive model approval required",
                "pricing_usd_per_million": KIMI_PRICING["kimi-k3"],
                "task_success": None,
                "tool_discipline": None,
                "decision": "BENCHMARK_DEFERRED_NO_CREDENTIAL",
            },
        ],
    }
    (ARTIFACTS / "provider-comparison.json").write_text(
        json.dumps(provider_payload, indent=2), encoding="utf-8"
    )
    print(json.dumps({"workflow_results": len(results), "all_passed": all(row.passed for row in results)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
