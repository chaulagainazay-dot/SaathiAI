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
from saathi.connectors.testing.provider_simulator import SIMULATOR_VERSION, SCENARIOS


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

    except ProviderRegistryError as e:
        _print({"error": str(e)})
        return 2

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
