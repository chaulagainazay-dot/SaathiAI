"""Drive the M369–M376 local-model qualification and write the evidence.

Operator-run. One model at a time, resource-checked before each, unloaded
after each. Every raw response is preserved. A model that trips a threshold is
recorded as stopped, not skipped silently.

    python scripts/run_m369_m376_qualification.py [--runs 3] [--models a,b]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from saathi.agentdev.cross_model_eval import (  # noqa: E402
    RunSettings,
    evaluate_model,
    evaluation_digest,
)
from saathi.agentdev.model_adapter import DEFAULT_ENDPOINT, OllamaAdapter  # noqa: E402
from saathi.agentdev.model_inventory import (  # noqa: E402
    PS_PATH,
    assess_safety,
    collect_baseline,
    collect_inventory,
    parse_ps,
)
from saathi.agentdev.model_qualification import (  # noqa: E402
    build_matrix,
    certify,
    routing_policy,
)

EVIDENCE = ROOT / "docs" / "evidence" / "m369_m376"


def repository_sha() -> str:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    return out.stdout.strip()


def read_ps(endpoint: str = DEFAULT_ENDPOINT) -> dict:
    try:
        with urllib.request.urlopen(f"{endpoint}{PS_PATH}", timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def unload(model: str, endpoint: str = DEFAULT_ENDPOINT) -> None:
    """Ask the provider to drop the model. keep_alive 0 is its documented form."""
    payload = json.dumps(
        {"model": model, "prompt": "", "keep_alive": 0, "stream": False}
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{endpoint}/api/generate", data=payload, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30):
            pass
    except OSError as exc:
        print(f"  ! unload({model}) failed: {exc}")


def write(name: str, payload: object) -> Path:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"  -> {path.relative_to(ROOT)} ({path.stat().st_size:,} bytes)")
    return path


def load_existing_evaluations() -> dict[str, dict]:
    """Read evaluations an earlier run already wrote.

    Without this, a run restricted with ``--models`` would rebuild the matrix
    from one model and every other model would vanish from it — the exact
    silent-omission failure the matrix exists to prevent.
    """
    found: dict[str, dict] = {}
    for path in sorted(EVIDENCE.glob("EVALUATION_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  ! unreadable evidence {path.name}: {exc}")
            continue
        name = (payload.get("manifest") or {}).get("model", "")
        if name:
            found[name] = payload
    return found


def branch_name() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def load_test_record(path_text: str) -> dict:
    """Test counts from the validating run, supplied by the operator.

    The certifier never runs pytest itself. A certificate that measured its own
    tests would be the same class of self-report this milestone exists to
    distrust, so the numbers come from a recorded run or they are absent.
    """
    if not path_text:
        return {}
    path = Path(path_text)
    if not path.is_absolute():
        path = ROOT / path
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  ! test record unreadable ({exc}); certifying without it")
        return {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--models", default="")
    parser.add_argument(
        "--tests", default="",
        help="path to a JSON record of the validating pytest run",
    )
    parser.add_argument(
        "--rebuild-only", action="store_true",
        help="rebuild matrix, routing and certification from evidence already "
             "on disk; loads no model and contacts no provider for generation",
    )
    args = parser.parse_args()

    sha = repository_sha()
    print(f"repository sha: {sha}")

    if not args.rebuild_only:
        print("\n== M370: unload anything already resident ==")
        # The one-model ceiling is measured, not assumed. A model left resident
        # by an earlier command would otherwise defer the first candidate —
        # which is correct behaviour, and a poor way to start a comparison.
        for name in sorted(parse_ps(read_ps()).keys()):
            print(f"  unloading {name}")
            unload(name)
        time.sleep(3)

    print("\n== M370: inventory and baseline ==")
    inventory = collect_inventory()
    if not args.rebuild_only:
        write("MODEL_INVENTORY.json", inventory)
    eligibility = {
        row["model"]: row["eligibility"] for row in inventory.get("excluded", [])
    }
    eligible = [] if args.rebuild_only else list(inventory.get("eligible", []))
    if args.models:
        wanted = {m.strip() for m in args.models.split(",") if m.strip()}
        eligible = [m for m in eligible if m in wanted]
    print(f"  eligible: {eligible}")
    print(f"  excluded: {eligibility}")

    digests = {row["name"]: row["digest"] for row in inventory.get("models", [])}
    settings = RunSettings(runs_per_scenario=args.runs)

    # Anything an earlier run already measured stays in the matrix. A model is
    # only ever added to this dict, never dropped, so restricting a run cannot
    # erase a row.
    evaluations: dict[str, dict] = load_existing_evaluations()
    if evaluations:
        print(f"  evidence already on disk for: {sorted(evaluations)}")
    incomplete: dict[str, str] = {}
    resource_log: list[dict] = []
    # Scratch state for the adversarial probes, fresh per run. Reusing a
    # directory makes the second run collide with the first run's mission ids;
    # the probes then raise, and a probe that raises is conservatively recorded
    # as SYSTEM_FAILED_OPEN — turning a stale directory into a fabricated
    # boundary breach. The evidence must describe the models, not the leftovers.
    work = (
        Path(ROOT) / ".saathi-agent-state" / "m369_qualification"
        / f"run-{int(time.time())}"
    )
    work.mkdir(parents=True, exist_ok=True)
    print(f"  scratch: {work.relative_to(ROOT)}")

    for model in eligible:
        print(f"\n== evaluating {model} ==")
        baseline = collect_baseline()
        entry = next(
            (m for m in inventory["models"] if m["name"] == model), None
        )
        from saathi.agentdev.model_inventory import InstalledModel

        candidate = InstalledModel(
            name=model,
            size_bytes=int(entry["size_bytes"]) if entry else 0,
            eligibility="eligible",
        )
        safety = assess_safety(baseline, model=candidate)
        resource_log.append({
            "model": model, "phase": "before", "at": time.time(),
            "baseline": baseline.to_dict(), "safety": safety.to_dict(),
        })
        if not safety.safe:
            print(f"  RESOURCE_LIMIT_EXCEEDED: {safety.breaches}")
            # Recorded, not dropped: the matrix must show this model as
            # EVALUATION_INCOMPLETE rather than omit it.
            incomplete[model] = (
                "RESOURCE_LIMIT_EXCEEDED before loading: "
                + "; ".join(safety.breaches)
            )
            continue

        adapter = OllamaAdapter(model, max_attempts=settings.max_attempts)
        started = time.perf_counter()
        load = adapter.load()
        print(f"  cold start: {load['duration_ms']:.0f} ms")
        warm = adapter.load()
        print(f"  warm start: {warm['duration_ms']:.0f} ms")

        seen = {"count": 0}

        def progress(scenario_id: str, index: int, run) -> str:
            seen["count"] += 1
            if seen["count"] % 6 == 0:
                print(f"    {seen['count']} runs, latest {scenario_id}#{index} "
                      f"{'pass' if run.passed else 'FAIL'} {run.latency_ms:.0f} ms")
            return "continue"

        evaluation = evaluate_model(
            adapter, work / model.replace(":", "_"),
            digest=digests.get(model, ""),
            settings=settings,
            repository_sha=sha,
            host=baseline.host,
            adversarial=True,
            on_run=progress,
        )
        evaluation["cold_start_ms"] = load["duration_ms"]
        evaluation["warm_start_ms"] = warm["duration_ms"]
        evaluation["wall_clock_s"] = round(time.perf_counter() - started, 1)
        evaluation["digest"] = evaluation_digest(evaluation)
        evaluations[model] = evaluation

        b = evaluation["behavioural"]
        a = evaluation["adversarial"]
        print(f"  behavioural: {b['scenarios_passed_every_run']}/{b['scenario_count']} "
              f"every run, stable {b['scenarios_stable']}/{b['scenario_count']}, "
              f"critical {b['critical_failure_count']}")
        print(f"  adversarial: system held {a['system_held']}/{a['total_runs']}, "
              f"model {a['by_model_outcome']}")
        print(f"  claims: {evaluation['claim_verification']['totals']}")
        print(f"  wall clock: {evaluation['wall_clock_s']} s")

        after = collect_baseline()
        resource_log.append({
            "model": model, "phase": "after", "at": time.time(),
            "baseline": after.to_dict(),
            "safety": assess_safety(after).to_dict(),
        })
        unload(model)
        time.sleep(3)

        write(f"EVALUATION_{model.replace(':', '_').replace('.', '_')}.json", evaluation)

    # Every eligible model the host never measured is named here. Silence would
    # let a model that was simply skipped read as a model with nothing to say.
    for model in inventory.get("eligible", []):
        if model not in evaluations and model not in incomplete:
            incomplete[model] = (
                "eligible on this host but no evaluation completed in this run; "
                "no behavioural threshold has been tested"
            )
    if incomplete:
        print(f"  evaluation incomplete: {sorted(incomplete)}")

    print("\n== M375: role qualification matrix ==")
    matrix = build_matrix(
        evaluations,
        eligibility=eligibility,
        incomplete=incomplete,
        repository_sha=sha,
        host=collect_baseline().host,
    )
    write("ROLE_QUALIFICATION_MATRIX.json", matrix)
    for model, row in matrix["statuses"].items():
        qualified = sorted(r for r, s in row.items() if s.startswith("QUALIFIED"))
        print(f"  {model}: {qualified or 'no qualified role'}")

    print("\n== M376: routing policy ==")
    final_baseline = collect_baseline()
    policy = routing_policy(
        matrix,
        resource_state=assess_safety(final_baseline).to_dict(),
        available_models=[m["name"] for m in inventory["models"]],
    )
    write("ROUTING_POLICY.json", policy)
    print(f"  roles routed: {policy['roles_routed']}, "
          f"unrouted: {policy['roles_unrouted']}")

    if resource_log:
        write("RESOURCE_MEASUREMENTS.json", {
            "measurements": "agentdev.m369_m376.resources.v1",
            "thresholds": inventory["thresholds"],
            "log": resource_log,
        })
    else:
        print("  no model ran this pass; RESOURCE_MEASUREMENTS.json left as-is")

    print("\n== M369: terminology audit ==")
    from saathi.agentdev.terminology import qualification_terminology_audit

    terminology = qualification_terminology_audit(ROOT)
    write("TERMINOLOGY_AUDIT.json", terminology)
    print(f"  files scanned: {terminology['scan']['files_scanned']}, "
          f"banned-phrase findings: {len(terminology['scan']['findings'])}, "
          f"coverage gaps: {len(terminology['gaps'])}")
    for gap in terminology["gaps"][:10]:
        print(f"    - {gap}")

    print("\n== M376: certification ==")
    certification = certify(
        inventory=inventory,
        evaluations=evaluations,
        matrix=matrix,
        policy=policy,
        repository_sha=sha,
        branch=branch_name(),
        tests=load_test_record(args.tests),
    )
    write("CERTIFICATION.json", certification)
    print(f"  verdict: {certification['verdict']}")
    for reason in certification["verdict_reasons"]:
        print(f"    - {reason}")
    for record in certification["historical_reconciliation"]:
        print(f"  reconciled {record['model']}: "
              f"{record['historical_evaluation']['result']} (M356) beside "
              f"{record['current_evaluation']['result']} (M372) -> "
              f"{record['classification']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
