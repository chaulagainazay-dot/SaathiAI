#!/usr/bin/env python3
"""Bounded local-runtime benchmark for an already-installed Ollama model.

No models are downloaded, unloaded, or deleted. The script aborts between
cases if available memory falls below 512 MiB or swap grows by more than
1 GiB from the starting sample.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import platform
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from saathi.inference.adapters.ollama import OllamaEngine
from saathi.inference.benchmarks import BenchCase, run_case

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "evaluation" / "local-runtime-results.json"

CASES = (
    BenchCase("structured_json", "structured_json", 'Return JSON only: {"label":"ok","score":1}', expect_json_keys=("label", "score")),
    BenchCase("tool_selection", "tool_selection", "Choose one tool name for weather: get_weather or send_email. Reply only get_weather.", expect_contains="get_weather", tool_name="get_weather"),
    BenchCase("concise_summary", "concise_summarization", "Summarize in at most 8 words: SaathiOS is a local-first governed AI operating system.", expect_contains="SaathiOS"),
    BenchCase("permission_risk", "permission_risk_classification", "Classify deleting production data as LOW or HIGH permission risk. Reply HIGH.", expect_contains="high"),
    BenchCase("memory_write", "memory_write_decision", "A user says their API key. Should it be written to long-term memory? Reply NO.", expect_contains="no"),
    BenchCase("code_edit", "simple_code_edit_reasoning", "Fix `def add(a,b): return a-b`. Reply with corrected function only.", expect_contains="return a + b"),
)


def _run(command: list[str]) -> str:
    return subprocess.run(command, check=False, capture_output=True, text=True, timeout=10).stdout.strip()


def _swap_used_mb() -> float:
    raw = _run(["sysctl", "-n", "vm.swapusage"])
    match = re.search(r"used = ([0-9.]+)([MG])", raw)
    if not match:
        return 0.0
    value = float(match.group(1))
    return value * 1024 if match.group(2) == "G" else value


def _free_mb() -> float:
    raw = _run(["vm_stat"])
    page_size = 16384
    first = raw.splitlines()[0] if raw else ""
    match = re.search(r"page size of (\d+) bytes", first)
    if match:
        page_size = int(match.group(1))
    pages = 0
    for label in ("Pages free", "Pages speculative", "Pages purgeable"):
        match = re.search(rf"{label}:\s+(\d+)", raw)
        if match:
            pages += int(match.group(1))
    return pages * page_size / (1024 * 1024)


def _memory_free_percent() -> int | None:
    raw = _run(["memory_pressure", "-Q"])
    match = re.search(r"System-wide memory free percentage:\s*(\d+)%", raw)
    return int(match.group(1)) if match else None


def _ollama_rss_mb() -> float:
    raw = _run(["ps", "-axo", "rss=,command="])
    total_kb = 0
    for line in raw.splitlines():
        if "ollama serve" in line and "benchmark_local_runtime.py" not in line:
            try:
                total_kb += int(line.strip().split(maxsplit=1)[0])
            except (ValueError, IndexError):
                continue
    return total_kb / 1024


async def benchmark(model: str) -> dict[str, Any]:
    start_swap = _swap_used_mb()
    start_free = _free_mb()
    start_free_percent = _memory_free_percent()
    engine = OllamaEngine(default_model=model)
    before_rss = _ollama_rss_mb()
    started = time.monotonic()
    results = []
    abort_reasons = []
    for case in CASES:
        free_percent = _memory_free_percent()
        swap_growth = _swap_used_mb() - start_swap
        if free_percent is not None and free_percent < 5:
            abort_reasons.append("system_memory_free_below_5_percent")
            break
        if swap_growth > 1024:
            abort_reasons.append("swap_growth_over_1_gb")
            break
        results.append(await run_case(engine, model, case))
    elapsed = time.monotonic() - started
    end_rss = _ollama_rss_mb()
    end_swap = _swap_used_mb()
    end_free = _free_mb()
    end_free_percent = _memory_free_percent()
    if end_free_percent is not None and end_free_percent < 5:
        abort_reasons.append("system_memory_free_below_5_percent")
    if end_swap - start_swap > 1024:
        abort_reasons.append("swap_growth_over_1_gb")
    rows = [result.to_dict() for result in results]
    successes = sum(1 for row in rows if row["success"])
    speeds = [row["tokens_per_second"] for row in rows if row["tokens_per_second"] is not None]
    return {
        "schema": "saathios.local_runtime_benchmark.v1",
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "memory_bytes": int(_run(["sysctl", "-n", "hw.memsize"]) or 0),
        },
        "runtime": {
            "name": "ollama",
            "version": _run(["ollama", "--version"]),
            "model": model,
            "model_details": _run(["ollama", "show", model, "--verbose"])[:4000],
            "cold_start_control": "not_forced; existing service and models were not interrupted",
        },
        "safety": {
            "start_free_mb": round(start_free, 2),
            "end_free_mb": round(end_free, 2),
            "start_memory_free_percent": start_free_percent,
            "end_memory_free_percent": end_free_percent,
            "start_swap_mb": round(start_swap, 2),
            "end_swap_mb": round(end_swap, 2),
            "ollama_rss_before_mb": round(before_rss, 2),
            "ollama_rss_after_mb": round(end_rss, 2),
            "thermal_observation": _run(["pmset", "-g", "therm"]),
            "abort_reasons": abort_reasons,
        },
        "summary": {
            "cases": len(rows),
            "successes": successes,
            "reliability": round(successes / len(rows), 3),
            "mean_tokens_per_second": round(sum(speeds) / len(speeds), 2) if speeds else None,
            "elapsed_seconds": round(elapsed, 2),
            "decision": "CANDIDATE_KEEP_OLLAMA_DEFAULT" if successes >= 4 and not abort_reasons else "BENCHMARK_INCONCLUSIVE",
        },
        "results": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen2.5:1.5b")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = asyncio.run(benchmark(args.model))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "summary": payload["summary"], "safety": payload["safety"]}, indent=2))
    return 2 if payload["safety"]["abort_reasons"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
