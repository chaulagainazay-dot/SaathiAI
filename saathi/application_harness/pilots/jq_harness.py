"""M17.6 jq live application harness — a THIRD distinct application.

Wraps the system `jq` CLI (JSON transformation) in the harness contract, routed
through the SAME service → adapter → gateway path. Pure data transformation: no
side effects, no network. The untrusted jq FILTER is validated against a denylist
(env/$ENV/input/include/import/getpath/@sh/... — anything that reads the
environment, files, or shells out) and length-bounded; input is read from a
file-root-confined path; output is independently verified as valid JSON.
"""
from __future__ import annotations

import json
import re
import shutil

from saathi.application_harness.models import (
    HarnessDefinition, HarnessOperation, TrustStatus, SideEffect,
)

# jq builtins/constructs that leak env / read files / shell-escape → rejected in
# an untrusted filter.
_FORBIDDEN_FILTER = re.compile(
    r"(?i)(\benv\b|\$ENV\b|\binput\b|\binputs\b|\binclude\b|\bimport\b|"
    r"\bgetpath\b|\binput_filename\b|\bmodulemeta\b|@sh\b|\$__loc__\b|\bdebug\b)")


def jq_path() -> str | None:
    return shutil.which("jq")


def available() -> dict:
    p = jq_path()
    return {"jq": p, "available": bool(p)}


def definition() -> HarnessDefinition:
    present = available()["available"]
    return HarnessDefinition(
        harness_id="jq", display_name="jq JSON", application_name="jq",
        application_vendor="jq", version="system" if present else "unknown",
        source_type="local", license="MIT",
        install_method="system_executable", entrypoint=jq_path() or "jq",
        required_executables=["jq"], risk_ceiling=1,
        supported_operations=["transform"],
        verification_strategy="valid_json_output",
        trust_status=(TrustStatus.APPROVED.value if present
                      else TrustStatus.DISCOVERED.value),
        validation_status="wrapped_canonical" if present else "dependency_blocked")


def operations() -> list[HarnessOperation]:
    return [
        HarnessOperation("transform", "jq", "Transform JSON", risk=0,
                         side_effect_type=SideEffect.NONE.value,
                         allowed_file_access="roots", idempotency_behavior="idempotent",
                         verification_rules=["json_stdout"]),
    ]


def validate_filter(flt: str) -> tuple[bool, str]:
    if not flt or len(flt) > 2000:
        return False, "HARNESS_ARGUMENT_REJECTED:filter_size"
    if _FORBIDDEN_FILTER.search(flt):
        return False, "HARNESS_ARGUMENT_REJECTED:forbidden_filter"
    return True, "ok"


def build_argv(*, filter_expr: str, input_path: str) -> list[str]:
    # -c compact, -e exit-status; input from a confined file; NO --rawfile/
    # --slurpfile (file reads) and NO --args (arg injection).
    return [jq_path() or "jq", "-c", "-e", filter_expr, input_path]


# ── independent verification: jq stdout must be valid JSON (per line) ────────
def verify_json_stdout(stdout: str) -> dict:
    lines = [ln for ln in (stdout or "").splitlines() if ln.strip()]
    if not lines:
        return {"verified": False, "reason": "empty_output"}
    try:
        parsed = [json.loads(ln) for ln in lines]
        return {"verified": True, "records": len(parsed),
                "first_type": type(parsed[0]).__name__}
    except Exception as e:
        return {"verified": False, "reason": f"invalid_json:{str(e)[:80]}"}
