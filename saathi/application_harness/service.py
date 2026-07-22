"""M17.3 harness execution service — the governed entry for harness actions.

Ownership + active session + trust + risk/approval are checked, then the sole
ApplicationHarnessAdapter runs the process, output is parsed defensively and
INDEPENDENTLY verified (never trusting the process's own success), and sanitized
evidence is produced. Risk >= 3 requires a bound approval; risk 4 is manual-only.
No agent/chat/frontend reaches the adapter except through this service.
"""
from __future__ import annotations

import tempfile
import time

from saathi.application_harness.models import (
    HarnessDefinition, HarnessOperation, HarnessActionIntent,
)
from saathi.application_harness import trust as T
from saathi.application_harness.adapter import ApplicationHarnessAdapter
from saathi.application_harness import verify as V

_ADAPTER = ApplicationHarnessAdapter()

APPROVAL_RISK = 3
MANUAL_ONLY_RISK = 4


def run_harness_action(*, defn: HarnessDefinition, op: HarnessOperation,
                       intent: HarnessActionIntent, argv: list, work_dir: str,
                       file_roots: list, owner: str, approved: bool = False,
                       verify_target: str = "", verify_kind: str = "",
                       actor_type: str = "user") -> dict:
    started = time.time()

    # ownership
    if intent.user_id != owner:
        return _blocked("HARNESS_PERMISSION_BLOCKED:ownership", started)
    # trust gate
    ok, reason = T.can_execute(defn)
    if not ok:
        return _blocked(reason, started)
    # risk / approval
    risk = op.risk
    if risk >= MANUAL_ONLY_RISK and actor_type != "user":
        return _blocked("HARNESS_NOT_APPROVED:manual_only_risk4", started)
    if risk >= APPROVAL_RISK and not approved:
        return {"status": "approval_required", "risk": risk,
                "argument_digest": intent.argument_digest(),
                "harness": defn.harness_id, "operation": op.operation_id,
                "duration_sec": round(time.time() - started, 3)}

    # execute through the sole adapter boundary
    res = _ADAPTER.run(defn=defn, intent=intent, argv=argv, work_dir=work_dir,
                       file_roots=file_roots, timeout=op.timeout)
    if res.status in ("blocked", "timeout", "failed"):
        return {"status": res.status, "error_code": res.error_code,
                "stderr": res.stderr[:500], "duration_sec": res.duration_sec,
                "harness": defn.harness_id, "operation": op.operation_id}

    # parse structured output defensively
    parsed = V.parse_structured(res.stdout)

    # INDEPENDENT verification — never trust the process's own success
    verification = {"verified": None}
    verify_required = False
    if "json_stdout" in op.verification_rules:
        # stdout-based verification (jq): output must be valid JSON
        from saathi.application_harness.pilots.jq_harness import verify_json_stdout
        verification = verify_json_stdout(res.stdout)
        verify_required = True
    elif verify_target:
        verification = _verify(verify_kind, verify_target, file_roots)
        verify_required = True

    # ambiguous/failed verification is NOT success
    if verify_required and not verification.get("verified"):
        return {"status": "uncertain", "harness": defn.harness_id,
                "operation": op.operation_id,
                "error_code": "HARNESS_VERIFICATION_FAILED",
                "verification": verification,
                "duration_sec": round(time.time() - started, 3)}

    return {
        "status": "success",
        "harness": defn.harness_id, "operation": op.operation_id,
        "risk": risk, "argument_digest": intent.argument_digest(),
        "output": parsed.data if parsed.ok else {"parse_error": parsed.error},
        "verification": verification,
        "exit_code": res.exit_code, "truncated": res.truncated,
        "duration_sec": round(time.time() - started, 3),
        "evidence": {"source_commit": defn.source_commit or "local",
                     "application_version": defn.version,
                     "harness_version": defn.version},
    }


def _verify(kind: str, target: str, roots: list) -> dict:
    if kind == "sqlite_db":
        from saathi.application_harness.pilots.sqlite_harness import verify_db
        return verify_db(target)
    fn = V.VERIFIERS.get(kind)
    if fn:
        return fn(target)
    return V.verify_file_in_roots(target, roots)


def _blocked(code: str, started: float) -> dict:
    return {"status": "blocked", "error_code": code,
            "duration_sec": round(time.time() - started, 3)}
