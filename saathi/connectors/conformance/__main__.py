"""CLI: python -m saathi.connectors.conformance <command>

Commands:
  assess <connector_id>
  assess-all
  status
  inspect <connector_id>
  verify
  revoke <connector_id> --reason <safe-reason>
  drift
  fingerprint <connector_id>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from saathi.connectors.conformance.assessor import assess_all, assess_connector, status_report
from saathi.connectors.conformance.drift import check_drift, verify_conformance
from saathi.connectors.conformance.fingerprint import fingerprint_report
from saathi.connectors.conformance.specification import specification_document
from saathi.connectors.conformance.store import get_certification_store
from saathi.connectors.registry.builtins import builtin_manifests

BUILTIN = {m.connector_id for m in builtin_manifests()}


def _print(obj: object) -> None:
    print(json.dumps(obj, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="saathi.connectors.conformance")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_assess = sub.add_parser("assess", help="Assess one registered connector")
    p_assess.add_argument("connector_id")

    sub.add_parser("assess-all", help="Assess all M29 built-ins")
    sub.add_parser("status", help="Show certification registry status")
    sub.add_parser("verify", help="Verify conformance + drift + bypasses")
    sub.add_parser("drift", help="Run certification drift check")
    sub.add_parser("spec", help="Dump conformance specification")

    p_ins = sub.add_parser("inspect", help="Inspect certification record")
    p_ins.add_argument("connector_id")

    p_fp = sub.add_parser("fingerprint", help="Compute certification fingerprint")
    p_fp.add_argument("connector_id")

    p_rev = sub.add_parser("revoke", help="Revoke connector certification")
    p_rev.add_argument("connector_id")
    p_rev.add_argument("--reason", required=True, help="Safe revocation reason")

    args = parser.parse_args(argv)
    store = get_certification_store()

    if args.cmd == "assess":
        cid = args.connector_id
        if cid not in BUILTIN and not cid.startswith("gov."):
            # Resolve only through registry — reject arbitrary import paths
            if "/" in cid or "\\" in cid or cid.endswith(".py"):
                print(json.dumps({"ok": False, "error": "import_path_rejected"}))
                return 2
        try:
            from saathi.connectors.gov.registry import get_registry
            # Ensure builtins present for assess
            from saathi.connectors.gov.runtime import GovernedConnectorRuntime
            rt = GovernedConnectorRuntime(rollout_mode="OFF", use_m26_incidents=False)
            rt.register_builtin_adapters()
        except Exception:
            pass
        result = assess_connector(cid, store=store)
        _print(result.to_dict())
        return 0 if result.state in ("CERTIFIED", "CERTIFIED_WITH_LIMITATIONS") else 1

    if args.cmd == "assess-all":
        try:
            from saathi.connectors.gov.runtime import GovernedConnectorRuntime
            rt = GovernedConnectorRuntime(rollout_mode="OFF", use_m26_incidents=False)
            rt.register_builtin_adapters()
        except Exception:
            pass
        results = assess_all(store=store)
        payload = {k: v.to_dict() for k, v in results.items()}
        _print(payload)
        ok = all(
            v.state in ("CERTIFIED", "CERTIFIED_WITH_LIMITATIONS")
            for v in results.values()
        )
        return 0 if ok else 1

    if args.cmd == "status":
        _print(status_report(store=store))
        return 0

    if args.cmd == "inspect":
        rec = store.get(args.connector_id)
        _print(rec.to_dict())
        return 0

    if args.cmd == "verify":
        rep = verify_conformance(store=store)
        _print(rep)
        return 0 if rep.get("ok") else 1

    if args.cmd == "drift":
        rep = check_drift(store=store)
        _print(rep)
        return 0 if rep.get("ok") else 1

    if args.cmd == "fingerprint":
        manifests = {m.connector_id: m for m in builtin_manifests()}
        m = manifests.get(args.connector_id)
        _print(fingerprint_report(connector_id=args.connector_id, manifest=m))
        return 0

    if args.cmd == "revoke":
        if not args.reason.strip():
            print(json.dumps({"ok": False, "error": "reason_required"}))
            return 2
        rec = store.revoke(args.connector_id, reason=args.reason.strip())
        _print({"ok": True, "record": rec.to_dict()})
        return 0

    if args.cmd == "spec":
        _print(specification_document())
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
