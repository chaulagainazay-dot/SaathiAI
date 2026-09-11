"""M376 — read-only console views over the local-model qualification evidence.

Thirteen panels built from the evidence the qualification run wrote. The module
reads JSON files and returns dictionaries; it holds no verb that could start a
model, change a route, approve a role, create a worktree, invoke a mission,
modify a file or stop a process, and :func:`capabilities` says so in a form a
test can assert rather than a sentence a reader has to trust.

Every panel degrades to ``status: "missing"`` when its evidence file is absent,
because a console that renders an empty table for missing evidence is a console
that quietly reports "nothing wrong".
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from saathi.agentdev.model_qualification import (
    AUTHORITY_BOUNDARY,
    NO_QUALIFIED_MODEL,
    OWNER_DECISION,
    QualificationStatus,
)

QUALIFICATION_CONSOLE_VERSION = "agentdev.qualification_console.v1"

EVIDENCE_DIRECTORY = "docs/evidence/m369_m376"

INVENTORY_FILE = "MODEL_INVENTORY.json"
MATRIX_FILE = "ROLE_QUALIFICATION_MATRIX.json"
ROUTING_FILE = "ROUTING_POLICY.json"
RESOURCE_FILE = "RESOURCE_MEASUREMENTS.json"
CERTIFICATION_FILE = "CERTIFICATION.json"


def _load(directory: Path, name: str) -> dict[str, Any] | None:
    path = directory / name
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _evaluations(directory: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted(directory.glob("EVALUATION_*.json")):
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(loaded, dict):
            loaded["_source"] = path.name
            out.append(loaded)
    return out


def _missing(name: str) -> dict[str, Any]:
    return {
        "status": "missing",
        "detail": f"{name} has not been generated; run the qualification suite",
    }


# --------------------------------------------------------------------------
# Panels
# --------------------------------------------------------------------------


def panel_installed_models(inventory: dict[str, Any] | None) -> dict[str, Any]:
    if not inventory:
        return _missing(INVENTORY_FILE)
    rows = [
        {
            "model": m["name"],
            "digest": m["digest_short"],
            "size_gib": m["size_gib"],
            "quantization": m["quantization"],
            "family": m["family"],
            "parameters": m["parameter_size"],
            "context": m["context_length"],
            "eligibility": m["eligibility"],
            "reason": m["exclusion_reason"],
        }
        for m in inventory.get("models", [])
    ]
    return {
        "status": "ok",
        "count": len(rows),
        "eligible": len(inventory.get("eligible", [])),
        "excluded": len(inventory.get("excluded", [])),
        "duplicate_digests": inventory.get("duplicate_digests", {}),
        "missing_digest": inventory.get("missing_digest", []),
        "rows": rows,
    }


def panel_provider_state(inventory: dict[str, Any] | None) -> dict[str, Any]:
    if not inventory:
        return _missing(INVENTORY_FILE)
    baseline = inventory.get("baseline", {})
    resident = baseline.get("resident_models", {})
    return {
        "status": "ok",
        "reachable": bool(inventory.get("provider_reachable")),
        "endpoint": inventory.get("endpoint", ""),
        "resident_count": len(resident),
        "resident": [
            {"model": name, "size_gib": round(size / (1024 ** 3), 2)}
            for name, size in sorted(resident.items())
        ],
        "ceiling": (inventory.get("thresholds") or {}).get("max_resident_models"),
        "measured_at": baseline.get("measured_at"),
    }


def panel_evaluation_progress(
    inventory: dict[str, Any] | None, evaluations: list[dict[str, Any]]
) -> dict[str, Any]:
    eligible = list((inventory or {}).get("eligible", []))
    done = {e.get("manifest", {}).get("model") for e in evaluations}
    rows = []
    for model in eligible:
        evaluation = next(
            (e for e in evaluations if e.get("manifest", {}).get("model") == model), None
        )
        behavioural = (evaluation or {}).get("behavioural") or {}
        rows.append({
            "model": model,
            "state": "evaluated" if evaluation else "not evaluated",
            "runs": behavioural.get("run_count", 0),
            "runs_per_scenario": (
                (evaluation or {}).get("manifest", {})
                .get("settings", {}).get("runs_per_scenario", 0)
            ),
            "wall_clock_s": (evaluation or {}).get("wall_clock_s", 0),
            "aborted": behavioural.get("aborted", ""),
        })
    return {
        "status": "ok" if eligible else "missing",
        "eligible": len(eligible),
        "evaluated": len(done & set(eligible)),
        "outstanding": sorted(set(eligible) - done),
        "rows": rows,
    }


def panel_behavioural_results(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    if not evaluations:
        return _missing("EVALUATION_*.json")
    rows = []
    for evaluation in evaluations:
        behavioural = evaluation.get("behavioural") or {}
        rows.append({
            "model": behavioural.get("model", "?"),
            "scenarios": behavioural.get("scenario_count", 0),
            "passed_every_run": behavioural.get("scenarios_passed_every_run", 0),
            "stable": behavioural.get("scenarios_stable", 0),
            "unstable": behavioural.get("scenarios_unstable", []),
            "runs": behavioural.get("run_count", 0),
            "malformed_rate": behavioural.get("malformed_output_rate", 0.0),
            "timeouts": behavioural.get("timeout_count", 0),
            "latency_median_ms": (behavioural.get("latency_ms") or {}).get("median", 0),
            "by_dimension": behavioural.get("by_dimension", {}),
        })
    return {"status": "ok", "count": len(rows), "rows": rows}


def panel_adversarial_results(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    if not evaluations:
        return _missing("EVALUATION_*.json")
    rows = []
    for evaluation in evaluations:
        adversarial = evaluation.get("adversarial") or {}
        rows.append({
            "model": adversarial.get("model", "?"),
            "attacks": adversarial.get("attack_count", 0),
            "runs": adversarial.get("total_runs", 0),
            # Reported side by side, never combined into one number.
            "system": adversarial.get("by_system_outcome", {}),
            "model_outcome": adversarial.get("by_model_outcome", {}),
            "failed_open": adversarial.get("failed_open", []),
        })
    return {
        "status": "ok",
        "count": len(rows),
        "rows": rows,
        "note": (
            "System enforcement and model compliance are separate columns. A "
            "system block is not a model success."
        ),
    }


def panel_contradictions(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    if not evaluations:
        return _missing("EVALUATION_*.json")
    rows = []
    for evaluation in evaluations:
        behavioural = evaluation.get("behavioural") or {}
        claims = evaluation.get("claim_verification") or {}
        adversarial = evaluation.get("adversarial") or {}
        rows.append({
            "model": behavioural.get("model", "?"),
            "rubric_findings": [
                f for f in behavioural.get("critical_failures", [])
                if f.startswith("self-contradiction")
            ],
            "verifier_count": (claims.get("totals") or {}).get(
                "internal_contradictions", 0
            ),
            "adversarial_count": len(
                adversarial.get("model_contradicted_itself") or []
            ),
        })
    return {
        "status": "ok",
        "count": len(rows),
        "rows": rows,
        "note": (
            "A response that refuses an action and also reports it done is "
            "recorded here and is never counted as a refusal."
        ),
    }


def panel_unsupported_claims(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    if not evaluations:
        return _missing("EVALUATION_*.json")
    rows = []
    for evaluation in evaluations:
        claims = evaluation.get("claim_verification") or {}
        totals = claims.get("totals") or {}
        rows.append({
            "model": claims.get("model", "?"),
            "responses_examined": claims.get("responses_examined", 0),
            "responses_with_claims": claims.get("responses_with_claims", 0),
            "claims_detected": totals.get("claims_detected", 0),
            "unsupported_completion_claims": totals.get(
                "unsupported_completion_claims", 0
            ),
            "by_status": claims.get("by_status", {}),
        })
    return {"status": "ok", "count": len(rows), "rows": rows}


def panel_qualification_resources(
    resources: dict[str, Any] | None, inventory: dict[str, Any] | None
) -> dict[str, Any]:
    if not resources and not inventory:
        return _missing(RESOURCE_FILE)
    log = (resources or {}).get("log", [])
    thresholds = (resources or {}).get("thresholds") or (
        (inventory or {}).get("thresholds") or {}
    )
    rows = []
    for entry in log:
        baseline = entry.get("baseline", {})
        rows.append({
            "model": entry.get("model", ""),
            "phase": entry.get("phase", ""),
            "free_swap_mib": (baseline.get("swap") or {}).get("free_mib"),
            "available_mib": (baseline.get("pages") or {}).get("available_mib"),
            "free_percent": (baseline.get("pressure") or {}).get("free_percent"),
            "free_disk_gib": (baseline.get("host") or {}).get("disk_free_gib"),
            "safe": (entry.get("safety") or {}).get("safe"),
            "breaches": (entry.get("safety") or {}).get("breaches", []),
        })
    return {
        "status": "ok" if rows or thresholds else "missing",
        "thresholds": thresholds,
        "measurements": len(rows),
        "aborts": [r for r in rows if r["safe"] is False],
        "rows": rows,
    }


def panel_role_matrix(matrix: dict[str, Any] | None) -> dict[str, Any]:
    if not matrix:
        return _missing(MATRIX_FILE)
    return {
        "status": "ok",
        "models": matrix.get("models", []),
        "roles": matrix.get("roles", []),
        "statuses": matrix.get("statuses", {}),
        "qualified_by_role": matrix.get("qualified_by_role", {}),
        "role_records": matrix.get("role_records", []),
        "repository_sha": matrix.get("repository_sha", ""),
    }


def panel_disqualified_roles(matrix: dict[str, Any] | None) -> dict[str, Any]:
    if not matrix:
        return _missing(MATRIX_FILE)
    rows = []
    for assessment in matrix.get("assessments", []):
        if assessment["status"] in (
            QualificationStatus.QUALIFIED.value,
            QualificationStatus.QUALIFIED_WITH_HUMAN_REVIEW.value,
        ):
            continue
        rows.append({
            "model": assessment["model"],
            "role": assessment["role"],
            "status": assessment["status"],
            "unmet": assessment["unmet"],
        })
    return {
        "status": "ok",
        "count": len(rows),
        "roles_with_no_qualified_model": matrix.get(
            "roles_with_no_qualified_model", []
        ),
        "rows": rows,
        "note": (
            "resource_unsuitable and not_qualified are different findings: the "
            "first means the host never loaded the model."
        ),
    }


def panel_routing_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    if not policy:
        return _missing(ROUTING_FILE)
    return {
        "status": "ok",
        "roles_routed": policy.get("roles_routed", 0),
        "roles_unrouted": policy.get("roles_unrouted", 0),
        "default_behaviour": policy.get("default_behaviour", {}),
        "concurrency": policy.get("concurrency", {}),
        "rows": [
            {
                "role": d["role"],
                "selected": d["selected_model"],
                "candidates": d["candidates"],
                "fallback": d["fallback"],
                "human_review": d["human_review"],
                "reason": d["reason"],
            }
            for d in policy.get("decisions", [])
        ],
    }


def panel_owner_decisions(
    matrix: dict[str, Any] | None, certification: dict[str, Any] | None
) -> dict[str, Any]:
    """Decisions recorded, and decisions still waiting on the owner."""
    pending: list[dict[str, str]] = []
    if matrix:
        for role in matrix.get("roles_with_no_qualified_model", []):
            pending.append({
                "decision": f"role {role} has no qualified model",
                "detail": (
                    "the role routes to a deterministic workflow or a person "
                    "until the owner approves a different arrangement"
                ),
            })
        for record in matrix.get("role_records", []):
            pending.append({
                "decision": (
                    f"{record['model']} is qualified with human review for "
                    f"{record['qualified_role']}"
                ),
                "detail": (
                    "any expansion beyond this role, or any reduction of the "
                    "human-review requirement, needs explicit owner approval"
                ),
            })
    return {
        "status": "ok",
        "recorded": OWNER_DECISION,
        "authority_boundary": list(AUTHORITY_BOUNDARY),
        "pending": pending,
        "pending_count": len(pending),
        "certification": (certification or {}).get("verdict", "not recorded"),
    }


def panel_certification_status(certification: dict[str, Any] | None) -> dict[str, Any]:
    if not certification:
        return _missing(CERTIFICATION_FILE)
    return {
        "status": "ok",
        "verdict": certification.get("verdict", ""),
        "milestones": certification.get("milestones", []),
        "repository_sha": certification.get("repository_sha", ""),
        "limitations": certification.get("limitations", []),
    }


# --------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------


def capabilities() -> dict[str, bool]:
    """Every verb this console does not have. Asserted by the test suite."""
    return {
        "starts_models": False,
        "changes_routing": False,
        "approves_roles": False,
        "creates_worktrees": False,
        "invokes_missions": False,
        "modifies_files": False,
        "stops_processes": False,
        "contacts_provider": False,
        "polls": False,
        "writes": False,
    }


def _tally(counts: dict[str, int] | None) -> str:
    """A token tally as readable text: ``BLOCKED 15 · RECORDED_FAILURE 3``.

    The tokens keep their meaning and lose only the shared prefix, so the two
    layers stay legible side by side in one row without a dict repr.
    """
    if not counts:
        return "—"
    return " · ".join(
        f"{k.replace('SYSTEM_', '').replace('MODEL_', '')} {v}"
        for k, v in counts.items()
    )


def _portable(directory: Path) -> str:
    """The evidence path as it should appear in a committed page.

    Relative to the repository when it lives inside it, so a rendered console
    does not carry one machine's home directory into the repository.
    """
    try:
        from saathi.config import ROOT

        return str(Path(directory).resolve().relative_to(Path(ROOT).resolve()))
    except (ImportError, ValueError):
        return Path(directory).name


def collect_qualification_state(
    evidence_directory: Path | str | None = None,
) -> dict[str, Any]:
    """Every qualification panel, read from evidence. Writes nothing."""
    if evidence_directory is None:
        from saathi.config import ROOT

        directory = Path(ROOT) / EVIDENCE_DIRECTORY
    else:
        directory = Path(evidence_directory)

    inventory = _load(directory, INVENTORY_FILE)
    matrix = _load(directory, MATRIX_FILE)
    policy = _load(directory, ROUTING_FILE)
    resources = _load(directory, RESOURCE_FILE)
    certification = _load(directory, CERTIFICATION_FILE)
    evaluations = _evaluations(directory)

    return {
        "console": QUALIFICATION_CONSOLE_VERSION,
        "generated_at": time.time(),
        "read_only": True,
        "evidence_directory": str(directory),
        # Rendered pages are committed as evidence, so what they display has to
        # read the same on any machine. The absolute path stays available to
        # callers above; only the display form is made portable.
        "evidence_directory_display": _portable(directory),
        "panels": {
            "installed_models": panel_installed_models(inventory),
            "provider_state": panel_provider_state(inventory),
            "evaluation_progress": panel_evaluation_progress(inventory, evaluations),
            "behavioural_results": panel_behavioural_results(evaluations),
            "adversarial_results": panel_adversarial_results(evaluations),
            "contradictions": panel_contradictions(evaluations),
            "unsupported_claims": panel_unsupported_claims(evaluations),
            "resource_usage": panel_qualification_resources(resources, inventory),
            "role_matrix": panel_role_matrix(matrix),
            "routing_policy": panel_routing_policy(policy),
            "disqualified_roles": panel_disqualified_roles(matrix),
            "owner_decisions": panel_owner_decisions(matrix, certification),
            "certification": panel_certification_status(certification),
        },
        "capabilities": capabilities(),
        "limitation": (
            "A snapshot of evidence files, not a live view of the provider. "
            "Refreshing means running the render command again, and a panel "
            "whose evidence is absent says so rather than showing an empty "
            "table."
        ),
    }


def render_qualification_text(state: dict[str, Any]) -> str:
    """A terminal summary of the thirteen panels."""
    p = state["panels"]
    lines: list[str] = []
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(state["generated_at"]))
    lines.append(f"SaathiOS Local-Model Qualification Console — snapshot {stamp}")
    lines.append(
        f"evidence: {state.get('evidence_directory_display') or state['evidence_directory']}"
        "  (read-only, no polling)"
    )
    lines.append("")

    models = p["installed_models"]
    if models["status"] == "ok":
        lines.append(f"1  installed models       {models['count']} installed, "
                     f"{models['eligible']} eligible, {models['excluded']} excluded")
        for row in models["rows"]:
            lines.append(
                f"     {row['model']:<20} {row['digest']:<14} {row['size_gib']:>5} GiB  "
                f"{row['quantization']:<8} {row['eligibility']}"
            )
    else:
        lines.append(f"1  installed models       {models['detail']}")

    provider = p["provider_state"]
    if provider["status"] == "ok":
        lines.append(f"2  provider state         reachable={provider['reachable']}, "
                     f"{provider['resident_count']} resident "
                     f"(ceiling {provider['ceiling']})")
    else:
        lines.append(f"2  provider state         {provider['detail']}")

    progress = p["evaluation_progress"]
    lines.append(f"3  evaluation progress    {progress.get('evaluated', 0)}/"
                 f"{progress.get('eligible', 0)} evaluated"
                 + (f", outstanding {progress['outstanding']}"
                    if progress.get("outstanding") else ""))

    behavioural = p["behavioural_results"]
    if behavioural["status"] == "ok":
        lines.append(f"4  behavioural results    {behavioural['count']} model(s)")
        for row in behavioural["rows"]:
            lines.append(
                f"     {row['model']:<20} {row['passed_every_run']}/{row['scenarios']} "
                f"every run, {row['stable']}/{row['scenarios']} stable, "
                f"median {row['latency_median_ms']:.0f} ms"
            )
    else:
        lines.append(f"4  behavioural results    {behavioural['detail']}")

    adversarial = p["adversarial_results"]
    if adversarial["status"] == "ok":
        lines.append(f"5  adversarial results    {adversarial['count']} model(s)")
        for row in adversarial["rows"]:
            lines.append(f"     {row['model']:<20} system {row['system']}")
            lines.append(f"     {'':<20} model  {row['model_outcome']}")
    else:
        lines.append(f"5  adversarial results    {adversarial['detail']}")

    contradictions = p["contradictions"]
    if contradictions["status"] == "ok":
        for row in contradictions["rows"]:
            lines.append(
                f"6  contradictions         {row['model']:<20} "
                f"rubric {len(row['rubric_findings'])}, "
                f"verifier {row['verifier_count']}, "
                f"adversarial {row['adversarial_count']}"
            )
    else:
        lines.append(f"6  contradictions         {contradictions['detail']}")

    unsupported = p["unsupported_claims"]
    if unsupported["status"] == "ok":
        for row in unsupported["rows"]:
            lines.append(
                f"7  unsupported claims     {row['model']:<20} "
                f"{row['unsupported_completion_claims']} of "
                f"{row['claims_detected']} detected claims"
            )
    else:
        lines.append(f"7  unsupported claims     {unsupported['detail']}")

    resources = p["resource_usage"]
    if resources["status"] == "ok":
        lines.append(f"8  resource usage         {resources['measurements']} "
                     f"measurement(s), {len(resources['aborts'])} abort(s)")
        for row in resources["rows"][:8]:
            lines.append(
                f"     {row['model']:<20} {row['phase']:<7} swap "
                f"{row['free_swap_mib']} MiB, avail {row['available_mib']} MiB, "
                f"safe={row['safe']}"
            )
    else:
        lines.append(f"8  resource usage         {resources['detail']}")

    matrix = p["role_matrix"]
    if matrix["status"] == "ok":
        lines.append(f"9  role matrix            {len(matrix['models'])} model(s) x "
                     f"{len(matrix['roles'])} role(s)")
        for model, row in sorted(matrix["statuses"].items()):
            qualified = sorted(r for r, s in row.items() if s.startswith("QUALIFIED"))
            lines.append(f"     {model:<20} {qualified or 'no qualified role'}")
    else:
        lines.append(f"9  role matrix            {matrix['detail']}")

    routing = p["routing_policy"]
    if routing["status"] == "ok":
        lines.append(f"10 routing policy         {routing['roles_routed']} routed, "
                     f"{routing['roles_unrouted']} unrouted, fallback "
                     f"{routing['default_behaviour'].get('automatic_fallback')}")
        for row in routing["rows"]:
            lines.append(f"     {row['role']:<30} -> {row['selected']}")
    else:
        lines.append(f"10 routing policy         {routing['detail']}")

    disqualified = p["disqualified_roles"]
    if disqualified["status"] == "ok":
        lines.append(f"11 disqualified roles     {disqualified['count']} "
                     f"model-role pair(s) not qualified")
    else:
        lines.append(f"11 disqualified roles     {disqualified['detail']}")

    owner = p["owner_decisions"]
    lines.append(f"12 owner decisions        {owner['pending_count']} pending; "
                 f"recorded {owner['recorded']['decision_id']}")
    for entry in owner["pending"][:6]:
        lines.append(f"     - {entry['decision']}")

    certification = p["certification"]
    if certification["status"] == "ok":
        lines.append(f"13 certification          {certification['verdict']}")
    else:
        lines.append(f"13 certification          {certification['detail']}")

    lines.append("")
    lines.append(state["limitation"])
    return "\n".join(lines) + "\n"


def render_qualification_html(state: dict[str, Any]) -> str:
    """One self-contained page. No form, no button, no script."""
    import html

    from saathi.agentdev.console import _CSS, _card, _kv, _table

    def e(value: Any) -> str:
        return html.escape("" if value is None else str(value), quote=True)

    p = state["panels"]
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(state["generated_at"]))
    cards: list[str] = []

    models = p["installed_models"]
    cards.append(_card(
        "1 · installed local models",
        _table(
            ["model", "digest", "size GiB", "quant", "params", "context", "eligibility"],
            [
                [r["model"], r["digest"], r["size_gib"], r["quantization"],
                 r["parameters"], r["context"], r["eligibility"]]
                for r in models.get("rows", [])
            ],
        ) if models["status"] == "ok" else f'<p class="empty">{e(models["detail"])}</p>',
        wide=True,
    ))

    provider = p["provider_state"]
    cards.append(_card(
        "2 · provider state",
        _kv([
            ("reachable", provider.get("reachable")),
            ("endpoint", provider.get("endpoint")),
            ("resident models", provider.get("resident_count")),
            ("ceiling", provider.get("ceiling")),
        ]) if provider["status"] == "ok"
        else f'<p class="empty">{e(provider["detail"])}</p>',
    ))

    progress = p["evaluation_progress"]
    cards.append(_card(
        "3 · evaluation progress",
        _table(
            ["model", "state", "runs", "per scenario", "wall clock s"],
            [
                [r["model"], r["state"], r["runs"], r["runs_per_scenario"],
                 r["wall_clock_s"]]
                for r in progress.get("rows", [])
            ],
        ),
    ))

    behavioural = p["behavioural_results"]
    cards.append(_card(
        "4 · behavioural results",
        _table(
            ["model", "passed every run", "stable", "runs", "malformed", "median ms"],
            [
                [r["model"], f"{r['passed_every_run']}/{r['scenarios']}",
                 f"{r['stable']}/{r['scenarios']}", r["runs"],
                 r["malformed_rate"], r["latency_median_ms"]]
                for r in behavioural.get("rows", [])
            ],
        ) if behavioural["status"] == "ok"
        else f'<p class="empty">{e(behavioural["detail"])}</p>',
        wide=True,
    ))

    adversarial = p["adversarial_results"]
    cards.append(_card(
        "5 · adversarial results",
        (_table(
            ["model", "system enforcement", "model compliance", "failed open"],
            [
                # _table escapes every cell, so these are handed over as plain
                # text. Escaping here as well produced &#x27; in the rendered
                # page, and a dict repr is not a readable tally either way.
                [r["model"], _tally(r["system"]), _tally(r["model_outcome"]),
                 len(r["failed_open"])]
                for r in adversarial.get("rows", [])
            ],
        ) + f'<p class="sub">{e(adversarial.get("note", ""))}</p>')
        if adversarial["status"] == "ok"
        else f'<p class="empty">{e(adversarial["detail"])}</p>',
        wide=True,
    ))

    contradictions = p["contradictions"]
    cards.append(_card(
        "6 · contradiction findings",
        _table(
            ["model", "rubric", "verifier", "adversarial"],
            [
                [r["model"], len(r["rubric_findings"]), r["verifier_count"],
                 r["adversarial_count"]]
                for r in contradictions.get("rows", [])
            ],
        ) if contradictions["status"] == "ok"
        else f'<p class="empty">{e(contradictions["detail"])}</p>',
    ))

    unsupported = p["unsupported_claims"]
    cards.append(_card(
        "7 · unsupported claims",
        _table(
            ["model", "responses", "claims", "unsupported completions"],
            [
                [r["model"], r["responses_examined"], r["claims_detected"],
                 r["unsupported_completion_claims"]]
                for r in unsupported.get("rows", [])
            ],
        ) if unsupported["status"] == "ok"
        else f'<p class="empty">{e(unsupported["detail"])}</p>',
    ))

    resources = p["resource_usage"]
    cards.append(_card(
        "8 · resource usage",
        _table(
            ["model", "phase", "swap MiB", "available MiB", "free %", "disk GiB", "safe"],
            [
                [r["model"], r["phase"], r["free_swap_mib"], r["available_mib"],
                 r["free_percent"], r["free_disk_gib"], r["safe"]]
                for r in resources.get("rows", [])
            ],
        ) if resources["status"] == "ok"
        else f'<p class="empty">{e(resources["detail"])}</p>',
        wide=True,
    ))

    matrix = p["role_matrix"]
    if matrix["status"] == "ok":
        roles = matrix["roles"]
        matrix_body = _table(
            ["model", *roles],
            [
                [model, *[matrix["statuses"][model][role] for role in roles]]
                for model in matrix["models"]
            ],
        )
    else:
        matrix_body = f'<p class="empty">{e(matrix["detail"])}</p>'
    cards.append(_card("9 · role qualification matrix", matrix_body, wide=True))

    routing = p["routing_policy"]
    cards.append(_card(
        "10 · routing policy",
        (_table(
            ["role", "selected", "candidates", "fallback"],
            [
                [r["role"], r["selected"], ", ".join(r["candidates"]) or "—",
                 r["fallback"]]
                for r in routing.get("rows", [])
            ],
        ) + _kv(list((routing.get("default_behaviour") or {}).items())))
        if routing["status"] == "ok"
        else f'<p class="empty">{e(routing["detail"])}</p>',
        wide=True,
    ))

    disqualified = p["disqualified_roles"]
    cards.append(_card(
        "11 · disqualified roles",
        _table(
            ["model", "role", "status", "first unmet requirement"],
            [
                [r["model"], r["role"], r["status"],
                 (r["unmet"][0] if r["unmet"] else "—")]
                for r in disqualified.get("rows", [])[:60]
            ],
            wrap=3,
        ) if disqualified["status"] == "ok"
        else f'<p class="empty">{e(disqualified["detail"])}</p>',
        wide=True,
    ))

    owner = p["owner_decisions"]
    cards.append(_card(
        "12 · owner decisions",
        _kv([
            ("recorded", owner["recorded"]["decision_id"]),
            ("pending", owner["pending_count"]),
        ]) + _table(
            ["pending decision", "detail"],
            [[entry["decision"], entry["detail"]] for entry in owner["pending"][:40]],
            wrap=1,
        ),
        wide=True,
    ))

    certification = p["certification"]
    cards.append(_card(
        "13 · certification",
        _kv([
            ("verdict", certification.get("verdict")),
            ("repository sha", certification.get("repository_sha")),
        ]) if certification["status"] == "ok"
        else f'<p class="empty">{e(certification["detail"])}</p>',
    ))

    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>SaathiOS Local-Model Qualification Console</title>"
        f"<style>{_CSS}</style></head><body>"
        "<h1>SaathiOS Local-Model Qualification Console</h1>"
        f'<p class="sub">Snapshot {e(stamp)} · evidence '
        f"<code>{e(state.get('evidence_directory_display') or state['evidence_directory'])}</code></p>"
        '<div class="banner"><strong>Read-only.</strong> This page displays '
        "recorded evidence. It cannot start a model, change a route, approve a "
        "role, create a worktree, invoke a mission, modify a file or stop a "
        "process, and it does not poll — refreshing means running "
        "<code>python -m saathi.agentdev qualification render</code> again.</div>"
        f'<div class="grid">{"".join(cards)}</div>'
        f"<footer>{e(state['console'])} · {e(state['limitation'])}</footer>"
        "</body></html>\n"
    )
