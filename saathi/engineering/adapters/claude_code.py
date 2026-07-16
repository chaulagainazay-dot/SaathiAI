"""Claude Code session adapter — governed, optional, no unrestricted shell.

Starts `claude` with a fixed argv shape only. Does not pass secrets, does not
spawn child agents, does not merge/deploy.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from saathi.engineering.adapters.base import (
    AdapterLaunchError,
    AgentSessionAdapter,
    LaunchRequest,
)
from saathi.engineering.models import AgentSessionResult, SessionStatus

# Fixed binary name — not user-supplied paths with shell metacharacters
ALLOWED_BINARIES = ("claude",)
MAX_PROMPT_FILE_CHARS = 24_000


class ClaudeCodeAdapter(AgentSessionAdapter):
    name = "claude_code"

    def __init__(
        self,
        *,
        binary: str = "claude",
        max_output_chars: int = 8000,
        dry_run: bool = False,
    ):
        super().__init__(max_output_chars=max_output_chars)
        if binary not in ALLOWED_BINARIES:
            raise AdapterLaunchError(f"binary_not_allowlisted:{binary}")
        self.binary = binary
        self.dry_run = dry_run

    def _resolve_binary(self) -> str:
        path = shutil.which(self.binary)
        if not path:
            raise AdapterLaunchError("claude_cli_not_found")
        return path

    def start(self, request: LaunchRequest, *, allowed_root: str) -> AgentSessionResult:
        wd = self.validate_working_directory(request.working_directory, allowed_root)
        prompt = (request.prompt or "").strip()
        if not prompt:
            raise AdapterLaunchError("empty_prompt")
        if len(prompt) > MAX_PROMPT_FILE_CHARS:
            raise AdapterLaunchError("prompt_too_large")

        sid = request.session_id
        now = time.time()

        if self.dry_run:
            self._sessions[sid] = {
                "status": SessionStatus.COMPLETED.value,
                "started_at": now,
                "ended_at": now,
                "pid": None,
                "proc": None,
                "stdout": "dry_run: claude not executed\n",
                "stderr": "",
                "working_directory": str(wd),
                "dry_run": True,
            }
            return AgentSessionResult(
                session_id=sid,
                status=SessionStatus.COMPLETED.value,
                process_id=None,
                adapter=self.name,
                started_at=now,
                ended_at=now,
                exit_code=0,
                stdout_tail=self._tail("dry_run: claude not executed\n"),
                usage_note="dry_run",
            )

        bin_path = self._resolve_binary()
        # Write prompt to a session-local file under the store-like tmp inside wd/.saathi
        # Prefer data dir outside git if possible; fall back to temp under /tmp
        prompt_dir = Path(allowed_root) / "data" / "engineering" / "prompts"
        try:
            prompt_dir.mkdir(parents=True, exist_ok=True)
            prompt_path = prompt_dir / f"{sid}.md"
            prompt_path.write_text(prompt, encoding="utf-8")
        except Exception:
            import tempfile
            prompt_path = Path(tempfile.gettempdir()) / f"saathi_eng_{sid}.md"
            prompt_path.write_text(prompt, encoding="utf-8")

        # Fixed argv — no shell, no user-supplied flags that expand permissions
        # `claude -p` print mode with prompt file content via stdin
        argv = [bin_path, "-p", "--output-format", "text"]
        # Minimal env: strip obvious secrets from child
        child_env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
            "TERM": os.environ.get("TERM", "dumb"),
            "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        }
        for k, v in (request.env_allowlist or {}).items():
            if k.startswith("SAATHI_ENG_") or k in ("USER", "LOGNAME"):
                child_env[k] = v

        try:
            proc = subprocess.Popen(
                argv,
                cwd=str(wd),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=child_env,
                start_new_session=True,
            )
            # Feed prompt via stdin; non-blocking finish handled in poll
            assert proc.stdin is not None
            proc.stdin.write(prompt)
            proc.stdin.close()
        except Exception as exc:
            raise AdapterLaunchError(f"spawn_failed:{exc}") from exc

        self._sessions[sid] = {
            "status": SessionStatus.RUNNING.value,
            "started_at": now,
            "timeout_sec": request.timeout_sec,
            "pid": proc.pid,
            "proc": proc,
            "stdout": "",
            "stderr": "",
            "working_directory": str(wd),
            "prompt_path": str(prompt_path),
        }
        return AgentSessionResult(
            session_id=sid,
            status=SessionStatus.RUNNING.value,
            process_id=proc.pid,
            adapter=self.name,
            started_at=now,
            stdout_tail="",
        )

    def _harvest(self, s: dict[str, Any]) -> None:
        proc: subprocess.Popen | None = s.get("proc")
        if not proc:
            return
        try:
            out, err = proc.communicate(timeout=0.05)
            if out:
                s["stdout"] = (s.get("stdout") or "") + out
            if err:
                s["stderr"] = (s.get("stderr") or "") + err
        except subprocess.TimeoutExpired:
            # still running — read without waiting fully
            pass
        except Exception:
            pass

    def poll(self, session_id: str) -> AgentSessionResult:
        s = self._sessions.get(session_id)
        if not s:
            return AgentSessionResult(
                session_id=session_id,
                status=SessionStatus.FAILED.value,
                error="session_not_found",
                adapter=self.name,
            )
        if s.get("dry_run"):
            return AgentSessionResult(
                session_id=session_id,
                status=SessionStatus.COMPLETED.value,
                adapter=self.name,
                started_at=float(s["started_at"]),
                ended_at=float(s.get("ended_at") or s["started_at"]),
                exit_code=0,
                stdout_tail=self._tail(s.get("stdout", "")),
                usage_note="dry_run",
            )

        proc: subprocess.Popen | None = s.get("proc")
        now = time.time()
        started = float(s["started_at"])
        timeout = float(s.get("timeout_sec") or 3600)

        if proc and proc.poll() is None:
            if now - started > timeout:
                self.request_stop(session_id, force=True)
                s["status"] = SessionStatus.TIMED_OUT.value
                return AgentSessionResult(
                    session_id=session_id,
                    status=SessionStatus.TIMED_OUT.value,
                    process_id=s.get("pid"),
                    adapter=self.name,
                    started_at=started,
                    ended_at=now,
                    exit_code=124,
                    error="timeout",
                    stdout_tail=self._tail(s.get("stdout", "")),
                    stderr_tail=self._tail(s.get("stderr", "")),
                )
            # still running
            s["status"] = SessionStatus.RUNNING.value
            # detect usage limit phrases in partial output if any
            combined = (s.get("stdout") or "") + (s.get("stderr") or "")
            if "usage limit" in combined.lower() or "rate limit" in combined.lower():
                s["status"] = SessionStatus.USAGE_LIMIT.value
            return AgentSessionResult(
                session_id=session_id,
                status=s["status"],
                process_id=s.get("pid"),
                adapter=self.name,
                started_at=started,
                stdout_tail=self._tail(s.get("stdout", "")),
                stderr_tail=self._tail(s.get("stderr", "")),
            )

        # finished
        if proc is not None:
            try:
                out, err = proc.communicate(timeout=2)
                if out:
                    s["stdout"] = (s.get("stdout") or "") + out
                if err:
                    s["stderr"] = (s.get("stderr") or "") + err
            except Exception:
                pass
            code = proc.returncode
        else:
            code = s.get("exit_code", 1)

        s["ended_at"] = now
        if code == 0:
            s["status"] = SessionStatus.COMPLETED.value
        elif code is None:
            s["status"] = SessionStatus.CRASHED.value
        else:
            s["status"] = SessionStatus.FAILED.value

        combined = (s.get("stdout") or "") + (s.get("stderr") or "")
        if "usage limit" in combined.lower():
            s["status"] = SessionStatus.USAGE_LIMIT.value

        return AgentSessionResult(
            session_id=session_id,
            status=s["status"],
            process_id=s.get("pid"),
            adapter=self.name,
            started_at=started,
            ended_at=now,
            exit_code=code,
            stdout_tail=self._tail(s.get("stdout", "")),
            stderr_tail=self._tail(s.get("stderr", "")),
            error="" if code == 0 else f"exit_{code}",
        )

    def request_stop(self, session_id: str, *, force: bool = False) -> AgentSessionResult:
        s = self._sessions.get(session_id)
        if not s:
            return AgentSessionResult(
                session_id=session_id,
                status=SessionStatus.FAILED.value,
                error="session_not_found",
                adapter=self.name,
            )
        proc: subprocess.Popen | None = s.get("proc")
        now = time.time()
        if proc and proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                try:
                    proc.terminate()
                except Exception:
                    pass
            if force:
                try:
                    time.sleep(0.2)
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        s["status"] = SessionStatus.STOPPED.value
        s["ended_at"] = now
        return AgentSessionResult(
            session_id=session_id,
            status=SessionStatus.STOPPED.value,
            process_id=s.get("pid"),
            adapter=self.name,
            started_at=float(s["started_at"]),
            ended_at=now,
            exit_code=-9 if force else 0,
            error="force_stop" if force else "graceful_stop",
            stdout_tail=self._tail(s.get("stdout", "")),
        )
