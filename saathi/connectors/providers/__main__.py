"""CLI: python -m saathi.connectors.providers <command>

Safe commands (never print secrets, auth headers, cookies, raw credentials, or
raw private provider payloads):

  list
  inspect  <provider-id>
  health   <provider-id>
  simulate <provider-id> <scenario>
  shadow   <provider-id> <safe-operation>
  verify
  drift
  quarantine <provider-id> --reason <safe-reason>
  recover  <provider-id>
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from saathi.connectors.providers.adapters.echo_provider import EchoProviderAdapter
from saathi.connectors.providers.config import ProviderConfig
from saathi.connectors.providers.eligibility import resolve_execution_eligibility
from saathi.connectors.providers.health import ProviderHealthTracker
from saathi.connectors.providers.models import (
    ExecutionMode,
    ProviderExecutionContext,
)
from saathi.connectors.providers.quarantine import ProviderQuarantineStore
from saathi.connectors.providers.registry import ProviderRegistry, ProviderRegistryError
from saathi.connectors.providers.runtime import ProviderExecutionRuntime
from saathi.connectors.providers.verification import (
    ProviderVerificationStore,
    check_provider_drift,
    resolve_provider_verification,
    verify_provider,
)
from saathi.connectors.providers.external.models import ExternalProfileError
from saathi.connectors.providers.external.profiles import (
    list_external_profiles,
    resolve_external_profile,
    schema_for,
)
from saathi.connectors.providers.external.verification import (
    ExternalVerificationStore,
    check_external_drift,
    resolve_external_verification,
)
from saathi.connectors.providers.external.verify import (
    fixture_hash_for,
    plan_external_verification,
    run_live_verification,
)
from saathi.connectors.testing.provider_simulator import SIMULATOR_VERSION, SCENARIOS


_NON_PRODUCTION_BANNER = (
    "=== EXTERNAL READ-ONLY SHADOW VERIFICATION ===\n"
    "=== NOT PRODUCTION AUTHORITY — rollout stays OFF; no writes; no account ==="
)

_M34_BANNER = (
    "=== LIVE EXTERNAL READ-ONLY VERIFICATION ===\n"
    "=== NON-PRODUCTION — ROLLOUT REMAINS OFF — NO WRITE AUTHORITY ==="
)


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True, default=str))


def _config_for(identity: Any) -> ProviderConfig:
    return ProviderConfig(
        provider_id=identity.provider_id,
        environment=identity.environment,
        endpoint_reference="inprocess://saathi.echo",
        allowed_operations=tuple(identity.capabilities),
        side_effect_class=identity.side_effect_class,
        data_classification=identity.data_classification,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="saathi.connectors.providers")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="List registered providers")
    p_ins = sub.add_parser("inspect"); p_ins.add_argument("provider_id")
    p_h = sub.add_parser("health"); p_h.add_argument("provider_id")
    p_sim = sub.add_parser("simulate"); p_sim.add_argument("provider_id"); p_sim.add_argument("scenario")
    p_sh = sub.add_parser("shadow"); p_sh.add_argument("provider_id"); p_sh.add_argument("operation")
    sub.add_parser("verify", help="Verify (simulation) the pilot provider")
    sub.add_parser("drift", help="Provider verification drift check")
    p_q = sub.add_parser("quarantine"); p_q.add_argument("provider_id"); p_q.add_argument("--reason", required=True)
    p_r = sub.add_parser("recover"); p_r.add_argument("provider_id")

    # ── M33 external read-only provider commands ─────────────────────────────
    sub.add_parser("candidates", help="List external read-only provider candidates")
    p_ep = sub.add_parser("external-profile"); p_ep.add_argument("provider_id")
    p_epl = sub.add_parser("external-plan"); p_epl.add_argument("provider_id")
    p_epl.add_argument("--ack-read-only", action="store_true")
    p_epl.add_argument("--ack-network", action="store_true")
    p_epl.add_argument("--budget", type=int, default=1)
    p_ev = sub.add_parser("external-verify"); p_ev.add_argument("provider_id")
    p_ev.add_argument("--ack-read-only", action="store_true")
    p_ev.add_argument("--ack-network", action="store_true")
    p_ev.add_argument("--ack-non-production", action="store_true")
    p_ev.add_argument("--ack-call-budget", action="store_true")
    p_ev.add_argument("--budget", type=int, default=1)
    p_ev.add_argument("--max-calls", type=int, default=None)
    p_ev.add_argument("--m33", action="store_true", help="use the legacy M33 single-call path")
    p_es = sub.add_parser("external-status"); p_es.add_argument("provider_id")
    p_ed = sub.add_parser("external-drift"); p_ed.add_argument("provider_id")
    p_erv = sub.add_parser("external-revoke"); p_erv.add_argument("provider_id")
    p_eq = sub.add_parser("external-quarantine"); p_eq.add_argument("provider_id")
    p_eq.add_argument("--reason", required=True)
    p_erc = sub.add_parser("external-recover"); p_erc.add_argument("provider_id")

    # ── M34 live external verification / reliability / canary-readiness ───────
    p_rs = sub.add_parser("reliability-status"); p_rs.add_argument("provider_id")
    p_cr = sub.add_parser("canary-readiness"); p_cr.add_argument("provider_id")
    p_eld = sub.add_parser("external-live-drift"); p_eld.add_argument("provider_id")

    args = parser.parse_args(argv)
    registry = ProviderRegistry()
    vstore = ProviderVerificationStore()

    try:
        if args.cmd == "list":
            _print({"providers": registry.list_ids(), "simulator_version": SIMULATOR_VERSION})
            return 0

        if args.cmd == "inspect":
            ident = registry.resolve(args.provider_id)
            _print({"identity": ident.to_dict(), "m32_safe": registry.is_m32_safe(args.provider_id)})
            return 0

        if args.cmd == "health":
            ident = registry.resolve(args.provider_id)
            adapter = EchoProviderAdapter(identity=ident)
            _print({"provider_id": ident.provider_id, "health": adapter.health()})
            return 0

        if args.cmd == "simulate":
            if args.scenario not in SCENARIOS:
                _print({"error": "unknown_scenario", "known": sorted(SCENARIOS)})
                return 2
            ident = registry.resolve(args.provider_id)
            adapter = EchoProviderAdapter(identity=ident)
            config = _config_for(ident)
            adapter.prepare(config)
            rt = ProviderExecutionRuntime()
            ctx = ProviderExecutionContext(
                connector_id=ident.connector_id, provider_id=ident.provider_id,
                operation="echo", request_id="cli-sim", payload={"msg": "hello"},
                mode=ExecutionMode.SIMULATION.value, safe_metadata={"scenario": args.scenario},
            )
            res = rt.execute(adapter, ctx, config)
            _print({"result": res.to_dict()})
            return 0

        if args.cmd == "shadow":
            if not registry.is_m32_safe(args.provider_id):
                _print({"error": "provider_not_m32_safe", "refused": True})
                return 3
            ident = registry.resolve(args.provider_id)
            if args.operation not in ident.capabilities:
                _print({"error": "unsupported_operation"})
                return 2
            adapter = EchoProviderAdapter(identity=ident)
            config = _config_for(ident)
            adapter.prepare(config)
            rt = ProviderExecutionRuntime()
            ctx = ProviderExecutionContext(
                connector_id=ident.connector_id, provider_id=ident.provider_id,
                operation=args.operation, request_id="cli-shadow", payload={"msg": "hello"},
                mode=ExecutionMode.SHADOW.value, safe_metadata={"scenario": "success"},
            )
            res = rt.execute(adapter, ctx, config)
            out = res.to_dict()
            out["authoritative"] = False
            _print({"result": out, "note": "shadow_result_non_authoritative"})
            return 0

        if args.cmd == "verify":
            ident = registry.resolve("saathi.echo.v1")
            config = _config_for(ident)
            rec = verify_provider(
                ident.provider_id, identity=ident, config=config,
                simulator_version=SIMULATOR_VERSION, store=vstore,
            )
            _print({"verification": rec.to_dict()})
            return 0

        if args.cmd == "drift":
            ident = registry.resolve("saathi.echo.v1")
            config = _config_for(ident)
            rep = check_provider_drift(
                ident.provider_id, identity=ident, config=config,
                simulator_version=SIMULATOR_VERSION, store=vstore, mark_stale=False,
            )
            _print(rep)
            return 0

        if args.cmd == "quarantine":
            store = ProviderQuarantineStore()
            rec = store.quarantine(args.provider_id, reason=args.reason)
            _print({"quarantine": rec.to_dict()})
            return 0

        if args.cmd == "recover":
            store = ProviderQuarantineStore()
            rec = store.recover(args.provider_id)
            _print({"recovered": rec.to_dict()})
            return 0

        # ── M33 external commands ────────────────────────────────────────────
        if args.cmd == "candidates":
            out = []
            for pid in list_external_profiles():
                p = resolve_external_profile(pid)
                out.append({
                    "provider_id": p.provider_id, "owner": p.provider_owner,
                    "documentation": p.official_documentation_reference,
                    "operation": p.operation, "method": p.method,
                    "side_effect_class": p.side_effect_class, "auth_profile": p.auth_profile,
                })
            _print({"candidates": out})
            return 0

        if args.cmd == "external-profile":
            p = resolve_external_profile(args.provider_id)
            _print({"external_profile": p.to_dict(), "schema": schema_for(p.provider_id).to_dict()})
            return 0

        if args.cmd == "external-plan":
            plan = plan_external_verification(
                args.provider_id, ack_read_only=args.ack_read_only,
                ack_network=args.ack_network, call_budget=args.budget,
            )
            _print(plan)
            return 0 if plan.get("allowed") else 3

        if args.cmd == "external-verify":
            if args.m33:
                # legacy M33 single-call path (kept for compatibility)
                print(_NON_PRODUCTION_BANNER)
                res = run_live_verification(
                    args.provider_id, ack_read_only=args.ack_read_only,
                    ack_network=args.ack_network, call_budget=args.budget,
                )
                _print(res)
                return 0 if res.get("ok") else 3
            # M34 governed live verification (default)
            from saathi.connectors.providers.external.m34 import (
                M34_DEFAULT_CALL_BUDGET, run_m34_live_verification, write_m34_evidence,
            )
            print(_M34_BANNER)
            max_calls = args.max_calls if args.max_calls is not None else M34_DEFAULT_CALL_BUDGET
            res = run_m34_live_verification(
                args.provider_id,
                ack_read_only=args.ack_read_only, ack_network=args.ack_network,
                ack_non_production=args.ack_non_production, ack_call_budget=args.ack_call_budget,
                max_calls=max_calls,
            )
            if res.get("live_call"):
                write_m34_evidence(res, evidence_dir="docs/evidence/m34")
            res.pop("_calls_internal", None)
            _print(res)
            return 0 if res.get("ok") else 3

        if args.cmd == "reliability-status":
            from saathi.connectors.providers.external.m34 import reliability_status
            _print(reliability_status(args.provider_id))
            return 0

        if args.cmd == "canary-readiness":
            from saathi.connectors.providers.external.m34 import canary_readiness_status
            _print(canary_readiness_status(args.provider_id))
            return 0

        if args.cmd == "external-live-drift":
            from saathi.connectors.providers.external.m34 import check_m34_drift
            _print(check_m34_drift(args.provider_id, mark_stale=False))
            return 0

        if args.cmd == "external-status":
            p = resolve_external_profile(args.provider_id)
            vstore = ExternalVerificationStore()
            rec = vstore.get(args.provider_id)
            dec = resolve_external_verification(
                args.provider_id, profile=p, schema=schema_for(p.provider_id),
                fixture_hash=fixture_hash_for(p.provider_id), store=vstore,
            )
            _print({"record": rec.to_dict(), "decision": dec.to_dict()})
            return 0

        if args.cmd == "external-drift":
            p = resolve_external_profile(args.provider_id)
            rep = check_external_drift(
                args.provider_id, profile=p, schema=schema_for(p.provider_id),
                fixture_hash=fixture_hash_for(p.provider_id), mark_stale=False,
            )
            _print(rep)
            return 0

        if args.cmd == "external-revoke":
            vstore = ExternalVerificationStore()
            rec = vstore.revoke(args.provider_id, reason="operator_revoke")
            _print({"revoked": rec.to_dict()})
            return 0

        if args.cmd == "external-quarantine":
            resolve_external_profile(args.provider_id)  # unknown fails closed
            store = ProviderQuarantineStore()
            rec = store.quarantine(args.provider_id, reason=args.reason)
            _print({"external_quarantine": rec.to_dict()})
            return 0

        if args.cmd == "external-recover":
            store = ProviderQuarantineStore()
            rec = store.recover(args.provider_id)
            _print({"external_recovered": rec.to_dict()})
            return 0

    except ExternalProfileError as e:
        _print({"error": f"external:{e}"})
        return 2
    except ProviderRegistryError as e:
        _print({"error": str(e)})
        return 2

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
