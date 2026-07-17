"""M20.7 console CLI — `python -m saathi.m20_console <cmd>`.

  status       unified engineering + inference read-only status
  flags        flag inventory + effective values
  disable      print disable procedure
  discover     CLI entrypoint map
  domains      isolation guarantees
  engineering  engineering snapshot only
  inference    inference snapshot only
  prod-config  M21.0 production config bundle (read-only)
  provider-governance  M21.2 provider availability/cost/circuit snapshot (read-only)
  residual-inference   M21.3 residual path + release-check snapshot (read-only)
  runtime-readiness    M21.4 consolidated runtime / production-config gate (read-only)

Never launches agents, never generates, never pushes.
"""
from __future__ import annotations

import json
import sys


def _emit(o) -> None:
    print(json.dumps(o, indent=1, default=str))


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    if cmd == "status":
        from saathi.m20_console.status import m20_console_status
        _emit(m20_console_status())
        return 0
    if cmd == "flags":
        from saathi.m20_console.flags import flag_snapshot
        _emit(flag_snapshot())
        return 0
    if cmd == "disable":
        from saathi.m20_console.flags import disable_procedure
        _emit(disable_procedure())
        return 0
    if cmd == "discover":
        from saathi.m20_console.status import cli_discovery
        _emit(cli_discovery())
        return 0
    if cmd == "domains":
        from saathi.m20_console.flags import domains_isolated
        _emit(domains_isolated())
        return 0
    if cmd == "engineering":
        from saathi.m20_console.status import engineering_snapshot
        _emit(engineering_snapshot())
        return 0
    if cmd == "inference":
        from saathi.m20_console.status import inference_snapshot
        _emit(inference_snapshot())
        return 0
    if cmd in ("prod-config", "prod_config", "m21"):
        from saathi.inference.prod_config import production_config_bundle
        _emit(production_config_bundle())
        return 0
    if cmd in ("provider-governance", "provider_governance", "m21_2"):
        from saathi.inference.provider_governance import governance_snapshot
        _emit(governance_snapshot())
        return 0
    if cmd in ("residual-inference", "residual_inference", "m21_3"):
        from saathi.inference.residual_paths import residual_paths_snapshot
        from saathi.inference.release_check import run_release_check

        snap = residual_paths_snapshot()
        rep = run_release_check()
        _emit(
            {
                "domain": "residual_inference",
                "milestone": "M21.3",
                "production_certified": False,
                "residual": {
                    "path_count": snap.get("path_count"),
                    "by_disposition": snap.get("by_disposition"),
                    "unknown_count": snap.get("unknown_count"),
                    "direct_provider_bypass_count": snap.get("direct_provider_bypass_count"),
                },
                "release_check": {
                    "ok": rep.ok,
                    "blocking_count": rep.blocking_count,
                    "files_scanned": rep.files_scanned,
                    "cli": "python -m saathi.inference.release_check",
                },
                "transitional_unknown": "disabled_forbidden",
            }
        )
        return 0
    if cmd in ("runtime-readiness", "runtime_readiness", "m21_4", "runtime-gate"):
        from saathi.inference.runtime_gate import runtime_readiness_snapshot

        _emit(runtime_readiness_snapshot())
        return 0
    _emit({"error": "unknown_command", "cmd": cmd, "hint": "help"})
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
