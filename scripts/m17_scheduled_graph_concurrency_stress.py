#!/usr/bin/env python3
"""M17 scheduled-graph concurrent recovery stress harness (certification).

Runs N iterations of W concurrent recover() callers against one interrupted
graph-backed occurrence and asserts:

  * exactly one recovered mission (run_count == 1)
  * occurrence ends SUCCEEDED (after bounded follow-up recovers)
  * graph pipeline resumed in place (one pipeline per correlation)
  * no orphan recovered-mission terminal-failure while graph succeeded

Does not use wall-clock performance thresholds. Deterministic injected runner
(no real sleeps). Exit 0 on full success; non-zero with a JSON summary on failure.

Usage:
  python scripts/m17_scheduled_graph_concurrency_stress.py \\
      --iterations 100 --workers 2 --seed 1
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import time
import traceback

# Allow running from a clean clone without install.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from saathi.application_harness import service as SVC
from saathi.application_harness.run_ledger import (
    RunLedger, OCC_SUCCEEDED, PIPELINE_SUCCEEDED, MISSION_COMPLETED, MISSION_FAILED,
)
from saathi.application_harness.pipeline import PipelineRunner
from saathi.application_harness.pipeline_graph import GraphPipelineRunner
from saathi.application_harness.mission import MissionEngine
from saathi.application_harness.scheduler import MissionScheduler
from saathi.application_harness.scheduled_graph import ScheduledGraphCoordinator


def _fail_on(produces: str, times: int, category: str = "transient_lock"):
    st = {"n": 0}
    lk = threading.Lock()

    def r(**kw):
        if any(str(a).endswith("/" + produces) for a in kw.get("argv", [])):
            with lk:
                if st["n"] < times:
                    st["n"] += 1
                    return {"status": "failed", "error_code": category}
        return SVC.run_harness_action(**kw)

    return r


def _build():
    led = RunLedger(os.path.join(tempfile.mkdtemp(prefix="m17stress_"), "l.db"))
    runs = tempfile.mkdtemp(prefix="m17runs_")
    runner = PipelineRunner(ledger=led, runner=_fail_on("b.db", 1), runs_root=runs)
    gr = GraphPipelineRunner(ledger=led, runner=runner)
    eng = MissionEngine(ledger=led, templates={}, pipeline_runner=runner, graph_runner=gr)
    sch = MissionScheduler(ledger=led, engine=eng)
    coord = ScheduledGraphCoordinator(ledger=led, engine=eng, scheduler=sch)
    return led, coord, sch, eng


def _one_occurrence(sch, *, now: float = 100.0):
    r = sch.create_schedule(
        owner="ajay", mission_template_id="graph_data_bundle",
        schedule_type="one_time", expression={"run_at": now + 10}, now=now)
    assert r["ok"], r
    gen = sch.create_due_occurrences(now=now + 20)
    assert len(gen["created"]) == 1
    return gen["created"][0]


def run_iteration(workers: int, *, timeout: float = 30.0) -> dict:
    led, coord, sch, eng = _build()
    oid = _one_occurrence(sch)
    coord.dispatch(oid, now=120.0)
    mid = led.inspect_occurrence(oid)["mission_id"]
    pid = eng.inspect(mid)["last_pipeline_id"]
    results: dict = {}
    barrier = threading.Barrier(workers)
    lock = threading.Lock()
    errors: list = []

    def go(i: int):
        try:
            barrier.wait(timeout=timeout)
            r = coord.recover(oid, now=200.0)
            with lock:
                results[i] = r
        except Exception as e:  # noqa: BLE001 — harness records genuine exceptions
            with lock:
                errors.append({"worker": i, "error": f"{type(e).__name__}: {e}",
                               "trace": traceback.format_exc()[-800:]})

    ts = [threading.Thread(target=go, args=(i,)) for i in range(workers)]
    t0 = time.monotonic()
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=timeout)
    duration = time.monotonic() - t0

    # Bounded follow-up recovers for contenders that returned in_progress.
    followups = 0
    for _ in range(max(3, workers)):
        if led.inspect_occurrence(oid)["state"] == OCC_SUCCEEDED:
            break
        coord.recover(oid, now=210.0 + followups)
        followups += 1

    occ = led.inspect_occurrence(oid)
    rec_id = eng._recovered_mission_id(mid)
    rec = eng.inspect(rec_id)
    graph = led.inspect_graph(pid, owner="ajay")
    pipelines = led.pipelines_for_correlation(mid)

    success_results = [r for r in results.values()
                       if r.get("ok") or r.get("state") == OCC_SUCCEEDED
                       or r.get("converged") or r.get("idempotent")]
    in_progress = [r for r in results.values()
                   if r.get("in_progress") or r.get("reason") == "resume_in_progress"
                   or r.get("state") == "retry_wait"]
    false_fail = [
        r for r in results.values()
        if r.get("state") == "failed" and not r.get("in_progress")
        and graph and graph.get("state") == PIPELINE_SUCCEEDED
        and rec and rec.get("state") == MISSION_COMPLETED
    ]

    ok = (
        not errors
        and occ["state"] == OCC_SUCCEEDED
        and rec is not None
        and rec["state"] == MISSION_COMPLETED
        and rec["run_count"] == 1
        and rec.get("last_pipeline_id") == pid
        and graph is not None
        and graph["state"] == PIPELINE_SUCCEEDED
        and len(pipelines) == 1
        and eng.inspect(mid)["state"] == MISSION_FAILED
        and not false_fail
    )
    return {
        "ok": ok,
        "duration_s": round(duration, 4),
        "followups": followups,
        "occurrence_state": occ["state"],
        "recovered_mission_state": (rec or {}).get("state"),
        "recovered_run_count": (rec or {}).get("run_count"),
        "pipeline_state": (graph or {}).get("state"),
        "pipeline_count": len(pipelines),
        "success_or_converged": len(success_results),
        "in_progress_or_retry": len(in_progress),
        "contention_false_failures": len(false_fail),
        "worker_errors": len(errors),
        "errors": errors,
        "worker_states": [r.get("state") for r in results.values()],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--iterations", type=int, default=100)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--seed", type=int, default=1, help="Reserved for future jitter; currently unused")
    p.add_argument("--timeout", type=float, default=30.0)
    p.add_argument("--json-out", type=str, default="")
    args = p.parse_args(argv)

    summary = {
        "iterations": args.iterations,
        "workers": args.workers,
        "seed": args.seed,
        "timeout": args.timeout,
        "successes": 0,
        "failures": 0,
        "contention_false_failures": 0,
        "duplicate_graphs": 0,
        "orphan_states": 0,
        "worker_errors": 0,
        "timeouts": 0,
        "duration_s": 0.0,
        "failed_iterations": [],
    }
    t0 = time.monotonic()
    for i in range(1, args.iterations + 1):
        try:
            r = run_iteration(args.workers, timeout=args.timeout)
        except Exception as e:  # noqa: BLE001
            summary["failures"] += 1
            summary["worker_errors"] += 1
            summary["failed_iterations"].append(
                {"iteration": i, "error": f"{type(e).__name__}: {e}"})
            continue
        summary["duration_s"] += r["duration_s"]
        summary["contention_false_failures"] += r["contention_false_failures"]
        summary["worker_errors"] += r["worker_errors"]
        if r["pipeline_count"] != 1:
            summary["duplicate_graphs"] += 1
        if r["ok"]:
            summary["successes"] += 1
        else:
            summary["failures"] += 1
            if r["occurrence_state"] not in (OCC_SUCCEEDED, "retry_wait") and (
                    r["pipeline_state"] == PIPELINE_SUCCEEDED):
                summary["orphan_states"] += 1
            if len(summary["failed_iterations"]) < 20:
                summary["failed_iterations"].append({"iteration": i, **r})
    summary["duration_s"] = round(time.monotonic() - t0, 4)
    summary["ok"] = summary["failures"] == 0 and summary["duplicate_graphs"] == 0
    text = json.dumps(summary, indent=2, sort_keys=True)
    if args.json_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.json_out)) or ".", exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
