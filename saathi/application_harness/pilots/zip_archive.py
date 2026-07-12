"""M17.7 zip archive live application harness — a FOURTH, distinct application.

Archive/packaging is a new category vs FFmpeg (media), SQLite (database) and jq
(JSON transform): it PRODUCES a container file that is itself an attack surface
(ZIP-slip path traversal, zip-bomb). Wraps the system `zip` / `unzip` CLIs in the
harness contract, routed through the SAME service -> adapter -> gateway path.

Security posture:
- pack: builds the archive with `-j` (junk paths) so our OWN output can only ever
  contain flat basenames — never a traversal entry — plus `-X` (drop uid/gid/extra
  attributes) and `-q`. Untrusted member names are validated first; input paths are
  file-root confined by the adapter. argv-only (never a shell string).
- list: read-only `unzip -l`; the tool's word is NOT trusted — verification opens
  the archive independently.
- Independent verification is `verify.verify_zip_safe`: it rejects ZIP-slip entries
  (leading `/` or `..`) and zip-bombs (ratio / uncompressed bound) by inspecting the
  container directly. This is the first LIVE exercise of that security verifier —
  every prior live app emitted media or JSON, never an archive. A hostile archive
  therefore verifies as NOT success even though the packaging tool exited 0.
"""
from __future__ import annotations

import re
import shutil

from saathi.application_harness.models import (
    HarnessDefinition, HarnessOperation, TrustStatus, SideEffect,
)
from saathi.application_harness import verify as V

# an untrusted archive-member name must be a plain relative basename-ish path:
# no leading slash, no `..` component, no NUL/control. Traversal is rejected at
# argument time (defense in depth on top of `-j` and the output verifier).
_BAD_MEMBER = re.compile(r"(^/|(^|/)\.\.(/|$)|\x00)")


def zip_path() -> str | None:
    return shutil.which("zip")


def unzip_path() -> str | None:
    return shutil.which("unzip")


def available() -> dict:
    z, u = zip_path(), unzip_path()
    return {"zip": z, "unzip": u, "available": bool(z and u)}


def definition() -> HarnessDefinition:
    present = available()["available"]
    return HarnessDefinition(
        harness_id="zip", display_name="Zip Archive", application_name="zip",
        application_vendor="Info-ZIP", version="system" if present else "unknown",
        source_type="local", license="Info-ZIP",
        install_method="system_executable", entrypoint=zip_path() or "zip",
        required_executables=["zip", "unzip"], risk_ceiling=1,
        supported_operations=["pack", "list_entries"],
        verification_strategy="zip_slip_and_bomb_safe",
        trust_status=(TrustStatus.APPROVED.value if present
                      else TrustStatus.DISCOVERED.value),
        validation_status="wrapped_canonical" if present else "dependency_blocked")


def operations() -> list[HarnessOperation]:
    return [
        HarnessOperation("pack", "zip", "Create archive", risk=1,
                         side_effect_type=SideEffect.LOCAL_REVERSIBLE.value,
                         allowed_file_access="roots", idempotency_behavior="conditional",
                         verification_rules=["zip"], reversibility="reversible"),
        HarnessOperation("list_entries", "zip", "List archive entries", risk=0,
                         side_effect_type=SideEffect.NONE.value,
                         allowed_file_access="roots", idempotency_behavior="idempotent",
                         verification_rules=["zip"]),
    ]


# ── untrusted-argument validation ───────────────────────────────────────────
def validate_member(name: str) -> tuple[bool, str]:
    if not name or len(name) > 1024:
        return False, "HARNESS_ARGUMENT_REJECTED:member_size"
    if _BAD_MEMBER.search(name):
        return False, "HARNESS_ARGUMENT_REJECTED:member_traversal"
    return True, "ok"


def validate_members(names: list[str]) -> tuple[bool, str]:
    if not names or len(names) > 4096:
        return False, "HARNESS_ARGUMENT_REJECTED:member_count"
    for n in names:
        ok, reason = validate_member(n)
        if not ok:
            return False, reason
    return True, reason if not names else "ok"


# ── argv builders (argv-only; caller supplies root-confined absolute paths) ──
def build_pack_argv(*, output_path: str, input_paths: list[str]) -> list[str]:
    # -q quiet, -X drop extra attrs, -j junk paths -> flat basenames only (our own
    # output can never contain a traversal entry). No -y: symlinks are followed and
    # stored as their target content, never as an escaping link.
    return [zip_path() or "zip", "-q", "-X", "-j", output_path, *input_paths]


def build_list_argv(*, archive_path: str) -> list[str]:
    # read-only listing; the tool's word is independently re-verified.
    return [unzip_path() or "unzip", "-l", archive_path]


# ── independent verification: reject ZIP-slip + zip-bomb by inspecting the
# container directly (never trusting zip/unzip's exit code) ──────────────────
def verify_archive(archive_path: str) -> dict:
    return V.verify_zip_safe(archive_path)
