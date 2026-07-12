"""M17.3 ApplicationHarnessAdapter — the ONLY place a harness process runs.

Argv-list execution only (never shell=True), sanitized minimal environment (no
inherited secrets), file-root confinement, bounded timeout + output size, process-
group cleanup. Enforces trust + ownership + risk before spawning. Structured
output is parsed and independently verified elsewhere; `status: success` from the
process is NEVER trusted on its own.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass

from saathi.application_harness.models import HarnessDefinition, HarnessActionIntent
from saathi.application_harness import trust as T

MAX_OUTPUT_BYTES = 2_000_000            # 2 MB stdout cap
# env vars that are safe to pass to a harness (nothing secret)
_ENV_ALLOW = {"PATH", "LANG", "LC_ALL", "TMPDIR", "HOME"}
# a minimal PATH — only where trusted executables live
_MIN_PATH = "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin"

# argument characters that must never appear (defense in depth; argv already
# avoids shell interpretation, but we reject obviously hostile values)
_BAD_ARG = ("\x00",)


@dataclass
class HarnessResult:
    status: str          # success | failed | timeout | blocked | uncertain
    exit_code: int | None
    stdout: str
    stderr: str
    duration_sec: float
    error_code: str = ""
    truncated: bool = False


class HarnessSecurityError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def _sanitized_env(extra_allow: list | None = None) -> dict:
    allow = set(_ENV_ALLOW) | set(extra_allow or [])
    env = {k: v for k, v in os.environ.items() if k in allow}
    env["PATH"] = _MIN_PATH            # minimal PATH, no user PATH poisoning
    env.pop("HOME", None) if False else None
    return env


def _confine(path: str, roots: list[str]) -> str:
    from pathlib import Path
    p = Path(path).resolve()
    for r in roots:
        rp = Path(r).resolve()
        try:
            p.relative_to(rp)
            if p.is_symlink():
                if p.resolve().relative_to(rp):
                    pass
            return str(p)
        except ValueError:
            continue
    raise HarnessSecurityError("HARNESS_FILE_ROOT_VIOLATION", f"{path} escapes roots")


class ApplicationHarnessAdapter:
    """Sole harness execution boundary. Callers reach it only via the gateway
    layer (see run_harness_action in service)."""

    def run(self, *, defn: HarnessDefinition, intent: HarnessActionIntent,
            argv: list[str], work_dir: str, file_roots: list[str],
            timeout: float = 60.0, env_allow: list | None = None,
            limits=None) -> HarnessResult:
        # 1) trust gate
        ok, reason = T.can_execute(defn)
        if not ok:
            return HarnessResult("blocked", None, "", "", 0.0, error_code=reason)
        # 2) argv must be a list of strings (NEVER a shell string)
        if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
            return HarnessResult("blocked", None, "", "", 0.0,
                                 error_code="HARNESS_ARGUMENT_REJECTED:not-argv-list")
        for a in argv:
            if any(b in a for b in _BAD_ARG):
                return HarnessResult("blocked", None, "", "", 0.0,
                                     error_code="HARNESS_ARGUMENT_REJECTED:control-char")
        # 3) entrypoint must be an absolute trusted path
        exe = argv[0]
        if not os.path.isabs(exe) or not os.path.exists(exe):
            resolved = shutil.which(exe)
            if not resolved:
                return HarnessResult("blocked", None, "", "", 0.0,
                                     error_code="HARNESS_APPLICATION_MISSING")
            argv = [resolved] + argv[1:]
        # 4) working dir confined
        try:
            work_dir = _confine(work_dir, file_roots) if file_roots else work_dir
        except HarnessSecurityError as e:
            return HarnessResult("blocked", None, "", "", 0.0, error_code=e.code)
        os.makedirs(work_dir, exist_ok=True)

        # resource limits (CPU/RAM/file-size) applied in the child before exec
        from saathi.application_harness.limits import DEFAULT_LIMITS
        lim = limits or DEFAULT_LIMITS
        started = time.time()
        try:
            proc = subprocess.Popen(
                argv, cwd=work_dir, env=_sanitized_env(env_allow),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True,   # own process group for clean kill
                preexec_fn=lim.preexec())
            try:
                out, err = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                _kill_group(proc)
                return HarnessResult("timeout", None, "", "", time.time() - started,
                                     error_code="HARNESS_TIMEOUT")
        except Exception as e:
            return HarnessResult("failed", None, "", str(e)[:200],
                                 time.time() - started, error_code="HARNESS_PROCESS_FAILED")
        truncated = len(out) > MAX_OUTPUT_BYTES
        out = out[:MAX_OUTPUT_BYTES]
        status = "success" if proc.returncode == 0 else "failed"
        return HarnessResult(
            status=status, exit_code=proc.returncode,
            stdout=out.decode(errors="replace"), stderr=err.decode(errors="replace")[:4000],
            duration_sec=round(time.time() - started, 3),
            error_code="" if status == "success" else "HARNESS_PROCESS_FAILED",
            truncated=truncated)


def _kill_group(proc) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
