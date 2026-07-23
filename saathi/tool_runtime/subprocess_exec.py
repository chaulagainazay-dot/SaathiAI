"""M49.2 bounded subprocess execution with honest cancellation classification."""
from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import asdict, dataclass, field
from typing import Callable, Sequence


class SubprocessCancelState:
    CANCELLATION_REQUESTED = "CANCELLATION_REQUESTED"
    TERMINATION_SENT = "TERMINATION_SENT"
    KILL_SENT = "KILL_SENT"
    PROCESS_EXIT_CONFIRMED = "PROCESS_EXIT_CONFIRMED"
    PROCESS_STILL_RUNNING = "PROCESS_STILL_RUNNING"
    CANCELLATION_UNCONFIRMED = "CANCELLATION_UNCONFIRMED"
    COMPLETED = "COMPLETED"
    TIMEOUT = "TIMEOUT"


@dataclass
class SubprocessResult:
    ok: bool
    exit_code: int | None
    stdout: str
    stderr: str
    cancel_state: str
    cancellation_confirmed: bool
    timeout_detected: bool
    pid: int | None = None
    duration_ms: float = 0.0
    argv: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def run_bounded(
    argv: Sequence[str],
    *,
    timeout_sec: float = 30.0,
    cwd: str | None = None,
    env: dict | None = None,
    cancel_check: Callable[[], bool] | None = None,
    grace_sec: float = 1.0,
    allow_kill: bool = True,
    max_stdout: int = 8000,
    max_stderr: int = 4000,
    shell: bool = False,
) -> SubprocessResult:
    """Run argv (no shell by default) with cancel/timeout polling.

    CANCELLED_CONFIRMED equivalent requires PROCESS_EXIT_CONFIRMED after signal.
    """
    if shell:
        raise ValueError("shell=True is not allowed in M49.2 bounded helper")
    if not argv:
        raise ValueError("argv required")
    start = time.time()
    # Minimal env: do not dump full environment secrets
    base_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", ""),
        "LANG": os.environ.get("LANG", "C"),
    }
    if env:
        for k, v in env.items():
            if k.upper() in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR"):
                base_env[k] = str(v)

    proc = subprocess.Popen(
        list(argv),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        env=base_env,
        start_new_session=True,
    )
    pid = proc.pid
    cancel_state = SubprocessCancelState.COMPLETED
    cancellation_confirmed = False
    timeout_detected = False
    deadline = start + max(0.05, float(timeout_sec))

    def _poll_done() -> bool:
        return proc.poll() is not None

    while not _poll_done():
        if cancel_check and cancel_check():
            cancel_state = SubprocessCancelState.CANCELLATION_REQUESTED
            _signal_group(proc, signal.SIGTERM)
            cancel_state = SubprocessCancelState.TERMINATION_SENT
            grace_end = time.time() + grace_sec
            while time.time() < grace_end and not _poll_done():
                time.sleep(0.02)
            if not _poll_done() and allow_kill:
                _signal_group(proc, signal.SIGKILL)
                cancel_state = SubprocessCancelState.KILL_SENT
                kill_end = time.time() + grace_sec
                while time.time() < kill_end and not _poll_done():
                    time.sleep(0.02)
            if _poll_done():
                cancel_state = SubprocessCancelState.PROCESS_EXIT_CONFIRMED
                cancellation_confirmed = True
            else:
                cancel_state = SubprocessCancelState.CANCELLATION_UNCONFIRMED
            break
        if time.time() >= deadline:
            timeout_detected = True
            cancel_state = SubprocessCancelState.TIMEOUT
            _signal_group(proc, signal.SIGTERM)
            grace_end = time.time() + grace_sec
            while time.time() < grace_end and not _poll_done():
                time.sleep(0.02)
            if not _poll_done() and allow_kill:
                _signal_group(proc, signal.SIGKILL)
                time.sleep(0.05)
            if _poll_done():
                cancel_state = SubprocessCancelState.PROCESS_EXIT_CONFIRMED
            else:
                cancel_state = SubprocessCancelState.PROCESS_STILL_RUNNING
            break
        time.sleep(0.02)

    stdout = ""
    stderr = ""
    try:
        out, err = proc.communicate(timeout=1.0)
        stdout = (out or "")[:max_stdout]
        stderr = (err or "")[:max_stderr]
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
        if cancel_state == SubprocessCancelState.COMPLETED:
            cancel_state = SubprocessCancelState.CANCELLATION_UNCONFIRMED

    code = proc.poll()
    finished = _poll_done()
    if cancellation_confirmed and not finished:
        cancellation_confirmed = False
        cancel_state = SubprocessCancelState.CANCELLATION_UNCONFIRMED
    if finished and cancel_state == SubprocessCancelState.COMPLETED:
        cancel_state = SubprocessCancelState.COMPLETED

    ok = (
        finished
        and code == 0
        and not cancellation_confirmed
        and not timeout_detected
    )
    return SubprocessResult(
        ok=ok,
        exit_code=code,
        stdout=stdout,
        stderr=stderr,
        cancel_state=cancel_state,
        cancellation_confirmed=cancellation_confirmed and finished,
        timeout_detected=timeout_detected,
        pid=pid,
        duration_ms=round((time.time() - start) * 1000, 2),
        argv=list(argv),
    )


def _signal_group(proc: subprocess.Popen, sig: int) -> None:
    try:
        if hasattr(os, "killpg"):
            os.killpg(os.getpgid(proc.pid), sig)
        else:
            proc.send_signal(sig)
    except Exception:
        try:
            proc.send_signal(sig)
        except Exception:
            pass
