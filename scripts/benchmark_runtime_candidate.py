#!/usr/bin/env python3
"""Bounded benchmark for the optional llama.cpp and MLX-LM candidates.

The harness uses the same six contract prompts as the Ollama benchmark. It
never changes the active provider, and it aborts between cases if macOS reports
less than five percent free memory or swap grows by more than one GiB.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "evaluation"

CASES = (
    ("structured_json", 'Return JSON only: {"label":"ok","score":1}', lambda value: _valid_json(value)),
    ("tool_selection", "Choose one tool name for weather: get_weather or send_email. Reply only get_weather.", lambda value: "get_weather" in value.lower()),
    ("concise_summary", "Summarize in at most 8 words: SaathiOS is a local-first governed AI operating system.", lambda value: "saathios" in value.lower()),
    ("permission_risk", "Classify deleting production data as LOW or HIGH permission risk. Reply HIGH.", lambda value: "high" in value.lower()),
    ("memory_write", "A user says their API key. Should it be written to long-term memory? Reply NO.", lambda value: _starts_with_no(value)),
    ("code_edit", "Fix `def add(a,b): return a-b`. Reply with corrected function only.", lambda value: "return a + b" in value),
)


def _run(command: list[str], timeout: int = 10) -> str:
    return subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout).stdout.strip()


def _run_combined(command: list[str], timeout: int = 10) -> str:
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    return (result.stdout or result.stderr).strip()


def _swap_used_mb() -> float:
    raw = _run(["sysctl", "-n", "vm.swapusage"])
    match = re.search(r"used = ([0-9.]+)([MG])", raw)
    if not match:
        return 0.0
    value = float(match.group(1))
    return value * 1024 if match.group(2) == "G" else value


def _memory_free_percent() -> int | None:
    match = re.search(r"System-wide memory free percentage:\s*(\d+)%", _run(["memory_pressure", "-Q"]))
    return int(match.group(1)) if match else None


def _valid_json(value: str) -> bool:
    try:
        parsed = json.loads(value.strip().removeprefix("```json").removesuffix("```").strip())
        return isinstance(parsed, dict) and {"label", "score"} <= parsed.keys()
    except (json.JSONDecodeError, AttributeError):
        return False


def _starts_with_no(value: str) -> bool:
    normalized = value.strip().lower().lstrip("*`#- ")
    return normalized == "no" or normalized.startswith(("no,", "no.", "no\n", "no "))


def _guard(start_swap: float) -> str | None:
    free_percent = _memory_free_percent()
    if free_percent is not None and free_percent < 5:
        return "system_memory_free_below_5_percent"
    if _swap_used_mb() - start_swap > 1024:
        return "swap_growth_over_1_gb"
    return None


def _llama_case(binary: str, model: str, prompt: str) -> dict[str, Any]:
    formatted_prompt = (
        "<|im_start|>system\nYou are Qwen, created by Alibaba Cloud. "
        "You are a helpful assistant.<|im_end|>\n"
        f"<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"
    )
    command = [
        "/usr/bin/time",
        "-l",
        binary,
        "-m",
        model,
        "--prompt",
        formatted_prompt,
        "--no-conversation",
        "--single-turn",
        "--simple-io",
        "--no-display-prompt",
        "--no-warmup",
        "--perf",
        "-ngl",
        "99",
        "--temp",
        "0",
        "--seed",
        "1",
        "--predict",
        "128",
    ]
    started = time.monotonic()
    completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=45)
    latency_ms = (time.monotonic() - started) * 1000
    stderr = completed.stderr
    speed = re.search(r"eval time\s*=\s*[\d.]+ ms\s*/\s*(\d+) runs\s*\(\s*([\d.]+) ms per token,\s*([\d.]+) tokens per second", stderr)
    load = re.search(r"load time\s*=\s*([\d.]+) ms", stderr)
    rss = re.search(r"^\s*(\d+)\s+maximum resident set size", stderr, re.MULTILINE)
    output = completed.stdout.strip()
    return {
        "output": output,
        "returncode": completed.returncode,
        "total_latency_ms": round(latency_ms, 2),
        "cold_load_ms": float(load.group(1)) if load else None,
        "tokens_per_second": float(speed.group(3)) if speed else None,
        "output_tokens": int(speed.group(1)) if speed else None,
        "peak_process_memory_mb": round(int(rss.group(1)) / (1024 * 1024), 2) if rss else None,
        "error": "" if completed.returncode == 0 else stderr[-500:],
    }


def _mlx_runner(model: str) -> tuple[Callable[[str], dict[str, Any]], dict[str, Any]]:
    import mlx.core as mx
    from mlx_lm import generate, load

    mx.reset_peak_memory()
    started = time.monotonic()
    loaded_model, tokenizer = load(model)
    load_ms = (time.monotonic() - started) * 1000

    def run(prompt: str) -> dict[str, Any]:
        messages = [{"role": "user", "content": prompt}]
        formatted = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        mx.reset_peak_memory()
        started_at = time.monotonic()
        response = generate(
            loaded_model,
            tokenizer,
            prompt=formatted,
            max_tokens=128,
            verbose=False,
        )
        elapsed = time.monotonic() - started_at
        token_count = len(tokenizer.encode(response))
        return {
            "output": response.strip(),
            "returncode": 0,
            "total_latency_ms": round(elapsed * 1000, 2),
            "cold_load_ms": None,
            "tokens_per_second": round(token_count / elapsed, 2) if elapsed else None,
            "output_tokens": token_count,
            "peak_process_memory_mb": round(mx.get_peak_memory() / (1024 * 1024), 2),
            "error": "",
        }

    return run, {"cold_load_ms": round(load_ms, 2), "mlx": importlib.metadata.version("mlx"), "mlx_lm": importlib.metadata.version("mlx-lm")}


def benchmark(runtime: str, model: str, binary: str) -> dict[str, Any]:
    start_swap = _swap_used_mb()
    start_free = _memory_free_percent()
    abort_reasons: list[str] = []
    results: list[dict[str, Any]] = []
    runtime_metadata: dict[str, Any]
    if runtime == "llama.cpp":
        runner = lambda prompt: _llama_case(binary, model, prompt)
        runtime_metadata = {"version": _run_combined([binary, "--version"]), "binary": binary}
    else:
        runner, runtime_metadata = _mlx_runner(model)

    for case_id, prompt, validator in CASES:
        reason = _guard(start_swap)
        if reason:
            abort_reasons.append(reason)
            break
        try:
            row = runner(prompt)
        except (subprocess.TimeoutExpired, RuntimeError, OSError) as exc:
            row = {
                "output": "",
                "returncode": 1,
                "total_latency_ms": None,
                "cold_load_ms": None,
                "tokens_per_second": None,
                "output_tokens": None,
                "peak_process_memory_mb": None,
                "error": f"{type(exc).__name__}: {exc}",
            }
        row["case_id"] = case_id
        row["success"] = row["returncode"] == 0 and validator(row["output"])
        row["output_preview"] = row.pop("output")[:240]
        results.append(row)

    speeds = [row["tokens_per_second"] for row in results if row["tokens_per_second"]]
    peak_memory = [row["peak_process_memory_mb"] for row in results if row["peak_process_memory_mb"]]
    successes = sum(bool(row["success"]) for row in results)
    return {
        "schema": "saathios.runtime_candidate_benchmark.v1",
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runtime": {"name": runtime, "model": model, **runtime_metadata},
        "safety": {
            "start_memory_free_percent": start_free,
            "end_memory_free_percent": _memory_free_percent(),
            "start_swap_mb": round(start_swap, 2),
            "end_swap_mb": round(_swap_used_mb(), 2),
            "thermal_observation": _run(["pmset", "-g", "therm"]),
            "abort_reasons": abort_reasons,
        },
        "summary": {
            "cases": len(results),
            "successes": successes,
            "reliability": round(successes / len(results), 3) if results else 0.0,
            "mean_tokens_per_second": round(sum(speeds) / len(speeds), 2) if speeds else None,
            "peak_process_memory_mb": max(peak_memory) if peak_memory else None,
            "decision": "BENCHMARK_ONLY" if results and not abort_reasons else "BENCHMARK_INCONCLUSIVE",
        },
        "results": results,
        "measurement_notes": {
            "time_to_first_token": "not available from these non-streaming candidate APIs",
            "mlx_speed": "output token count divided by end-to-end generation time",
            "llama_cpp_speed": "native llama.cpp eval timing",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", choices=("llama.cpp", "mlx-lm"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--binary", default="llama-completion")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or DEFAULT_OUTPUT_DIR / f"{args.runtime.replace('.', '-')}-results.json"
    payload = benchmark(args.runtime, args.model, args.binary)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "summary": payload["summary"], "safety": payload["safety"]}, indent=2))
    return 2 if payload["safety"]["abort_reasons"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
