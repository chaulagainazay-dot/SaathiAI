"""M21.2 / M24 — Provider governance facade and CLI.

  python -m saathi.inference.provider_governance providers
  python -m saathi.inference.provider_governance availability
  python -m saathi.inference.provider_governance costs
  python -m saathi.inference.provider_governance failures
  python -m saathi.inference.provider_governance circuits
  python -m saathi.inference.provider_governance decide
  python -m saathi.inference.provider_governance reset-circuit <provider_id> --confirm
  python -m saathi.inference.provider_governance force-open <provider_id> --confirm
  python -m saathi.inference.provider_governance reservations
  python -m saathi.inference.provider_governance recover-reservations
  python -m saathi.inference.provider_governance resolve-reservation <id> release|settle --confirm [--amount N]
  python -m saathi.inference.provider_governance readiness
  python -m saathi.inference.provider_governance disable

Never executes live inference. Never prints secrets.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Optional

from saathi.inference.availability import AvailabilityState, evaluate_availability
from saathi.inference.circuit_breaker import get_circuit_registry
from saathi.inference.cost_policy import estimate_cost, estimate_input_tokens
from saathi.inference.failure_taxonomy import taxonomy_snapshot
from saathi.inference.governance_errors import GovernanceError
from saathi.inference.governance_service import get_governance_service
from saathi.inference.governance_store import get_governance_store
from saathi.inference.provider_decision import decide_providers, privacy_safe_decision_telemetry
from saathi.inference.provider_descriptor import (
    descriptor_snapshot,
    get_descriptor,
    list_descriptors,
    validate_descriptor,
)
from saathi.inference.provider_policy import (
    disable_provider_commands,
    is_master_killed,
    is_provider_killed,
    provider_policy_snapshot,
)
from saathi.inference.request import InferenceRequest


def governance_snapshot() -> dict[str, Any]:
    circuits = get_circuit_registry()
    store = get_governance_store()
    providers = []
    for d in list_descriptors():
        killed = is_provider_killed(d.provider_id)
        allow, reason = circuits.allow_request(d.provider_id)
        snap = circuits.snapshot(d.provider_id)
        avail = evaluate_availability(
            d.provider_id,
            policy_enabled=d.enabled and not killed,
            configured=d.configured,
            credential_required=d.credential_required,
            credential_present=d.credential_present,
            production_supported=d.production_supported,
            production_context=False,
            provider_class=d.provider_class,
            killed=killed or is_master_killed(),
            circuit_open=(not allow and reason == "circuit_open"),
        )
        pricing = d.pricing
        cost_est = estimate_cost(
            pricing,
            input_tokens=500,
            output_tokens_ceiling=256,
        )
        providers.append(
            {
                "provider_id": d.provider_id,
                "local_or_cloud": d.local_or_cloud,
                "enabled": d.enabled,
                "configured": d.configured,
                "availability_state": avail.state.value,
                "availability_reason": avail.reason_code,
                "certification_state": d.certification_state,
                "circuit_state": snap.state.value,
                "kill_state": killed or is_master_killed(),
                "capabilities": list(d.supported_capabilities),
                "cost_status": cost_est.status.value,
                "pricing_freshness": cost_est.pricing_freshness,
                "cloud_data_processing": d.cloud_data_processing,
                "health_evidence_tier": avail.evidence_tier,
                "safe_reason": avail.explanation,
                "production_certified": False,
            }
        )
    ready = store.readiness()
    return {
        "schema": "m24.provider_governance.v1",
        "milestone": "M24",
        "production_certified": False,
        "kill_all": is_master_killed(),
        "cloud_fallback_default": False,
        "providers": providers,
        "circuit_process_local": False,
        "circuit_persistent": True,
        "durable_governance": ready,
        "cli": "python -m saathi.inference.provider_governance",
    }


def explain_decision(
    *,
    caller: str = "test_m21",
    prompt: str = "ping",
    local_only: bool = True,
    production_context: bool = False,
) -> dict[str, Any]:
    req = InferenceRequest(
        prompt=prompt,
        caller_component=caller,
        local_only=local_only,
        max_output_tokens=64,
        timeout_seconds=15.0,
    )
    dec = decide_providers(req, production_context=production_context)
    return {
        "decision": dec.to_dict(),
        "telemetry": privacy_safe_decision_telemetry(dec),
    }


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0

    def emit(o: Any) -> None:
        print(json.dumps(o, indent=1, default=str))

    cmd = argv[0]
    if cmd == "providers":
        emit(descriptor_snapshot())
        return 0
    if cmd == "availability":
        emit(governance_snapshot())
        return 0
    if cmd == "costs":
        rows = []
        for d in list_descriptors():
            est = estimate_cost(d.pricing, input_tokens=1000, output_tokens_ceiling=500)
            rows.append(
                {
                    "provider_id": d.provider_id,
                    "pricing": d.pricing.to_dict(),
                    "sample_estimate": est.to_dict(),
                    "validation_errors": validate_descriptor(d),
                }
            )
        emit({"schema": "m24.costs.v1", "providers": rows, "durable": True})
        return 0
    if cmd == "failures":
        emit(taxonomy_snapshot())
        return 0
    if cmd == "circuits":
        reg = get_circuit_registry()
        store = get_governance_store()
        emit(
            {
                "schema": "m24.circuits.v1",
                "process_local": False,
                "persistent": True,
                "circuits": [s.to_dict() for s in reg.all_snapshots()],
                "store": store.readiness(),
                "note": "Empty list means no provider has been attempted yet",
            }
        )
        return 0
    if cmd == "decide":
        caller = "test_m21"
        if len(argv) > 1 and not argv[1].startswith("-"):
            caller = argv[1]
        emit(explain_decision(caller=caller))
        return 0
    if cmd in ("reset-circuit", "reset_circuit"):
        if len(argv) < 2:
            emit({"ok": False, "error": "usage: reset-circuit <provider_id> --confirm"})
            return 2
        pid = argv[1]
        if "--confirm" not in argv:
            emit(
                {
                    "ok": False,
                    "error": "refusing mutate without --confirm",
                    "hint": f"python -m saathi.inference.provider_governance reset-circuit {pid} --confirm",
                }
            )
            return 2
        try:
            snap = get_governance_store().manual_reset(
                pid, confirm=True, actor_id="cli", reason_code="manual_reset"
            )
            emit({"ok": True, "circuit": snap})
            return 0
        except GovernanceError as e:
            emit({"ok": False, **e.to_dict()})
            return 2
    if cmd in ("force-open", "force_open"):
        if len(argv) < 2:
            emit({"ok": False, "error": "usage: force-open <provider_id> --confirm"})
            return 2
        pid = argv[1]
        if "--confirm" not in argv:
            emit({"ok": False, "error": "refusing mutate without --confirm"})
            return 2
        try:
            snap = get_governance_store().force_open(
                pid, confirm=True, actor_id="cli", reason_code="force_open"
            )
            emit({"ok": True, "circuit": snap})
            return 0
        except GovernanceError as e:
            emit({"ok": False, **e.to_dict()})
            return 2
    if cmd == "reservations":
        store = get_governance_store()
        emit(
            {
                "schema": "m24.reservations.v1",
                "unresolved": store.list_unresolved_reservations(),
                "readiness": store.readiness(),
            }
        )
        return 0
    if cmd in ("recover-reservations", "recover_reservations"):
        emit(get_governance_service().recover())
        return 0
    if cmd in ("resolve-reservation", "resolve_reservation"):
        if len(argv) < 3:
            emit(
                {
                    "ok": False,
                    "error": "usage: resolve-reservation <id> release|settle --confirm [--amount N]",
                }
            )
            return 2
        rid = argv[1]
        resolution = argv[2]
        if "--confirm" not in argv:
            emit({"ok": False, "error": "refusing mutate without --confirm"})
            return 2
        amount = None
        if "--amount" in argv:
            i = argv.index("--amount")
            if i + 1 < len(argv):
                amount = argv[i + 1]
        try:
            out = get_governance_store().operator_resolve_reservation(
                rid,
                resolution=resolution,
                actor_id="cli",
                reason_code="operator_cli",
                actual_cost=amount,
                confirm=True,
            )
            emit({"ok": True, "result": out})
            return 0
        except GovernanceError as e:
            emit({"ok": False, **e.to_dict()})
            return 2
    if cmd == "readiness":
        emit(get_governance_store().readiness())
        return 0
    if cmd == "disable":
        emit(disable_provider_commands())
        return 0
    if cmd == "validate":
        errs = {}
        for d in list_descriptors():
            e = validate_descriptor(d)
            if e:
                errs[d.provider_id] = e
        emit({"ok": not errs, "errors": errs, "count": len(list_descriptors())})
        return 0 if not errs else 1
    if cmd == "snapshot":
        emit(governance_snapshot())
        return 0
    emit({"ok": False, "error": f"unknown command {cmd}"})
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
