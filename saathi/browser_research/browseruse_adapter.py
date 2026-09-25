"""M — BROWSER_USE isolated agentic acquisition adapter (main-process side).

Imports ZERO browser-use symbols. Launches the isolated-venv runner as a bounded
subprocess, feeds it a public-research JSON request, and normalizes the JSON
result behind the FROZEN BrowserResearchProvider contract. Every failure is
contained into a typed degraded result — the SaathiOS process never crashes.

Authority: the subprocess receives ONLY the request (url/task/allowed_domains/
model/bounds) in a secret-stripped environment. No gateway, Trading Guardian,
broker, DB handle, credential, or market_data write is ever passed to it.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from saathi.browser.policy import check_domain, detect_prompt_injection
from saathi.browser_research.contract import FetchedPage
from saathi.browser_research.provider import BrowserResearchProvider
from saathi.browser_research.tiers import host_of

_RUNNER = str(Path(__file__).with_name("_browseruse_runner.py"))

# Typed degraded categories (Phase 14). None of these crash SaathiOS.
DEGRADED = {
    "BROWSER_USE_TIMEOUT", "BROWSER_USE_CRASH", "BROWSER_USE_RESOURCE_LIMIT",
    "BROWSER_USE_MODEL_UNAVAILABLE", "BROWSER_USE_INVALID_RESULT",
    "BROWSER_USE_DOMAIN_BLOCKED",
}

# Env keys that must NEVER reach the subprocess (defense against credential leak).
_SECRET_ENV_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "ANTHROPIC", "OPENAI",
                       "GEMINI", "GROQ", "GOOGLE", "AWS", "SAATHI_TOKEN", "BAADAR")


@dataclass
class BrowserUseConfig:
    isolated_python: str                      # path to the browser-use venv python
    runner_path: str = _RUNNER
    model: str = "qwen3:4b"
    ollama_host: str = "http://127.0.0.1:11434"
    max_steps: int = 12
    max_runtime_sec: float = 120.0
    model_timeout_sec: float = 90.0


def _child_env() -> dict:
    """Minimal, secret-stripped environment for the subprocess."""
    keep = {}
    # Allowlist only — nothing carrying a secret marker is ever forwarded.
    for k in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "PLAYWRIGHT_BROWSERS_PATH"):
        if k in os.environ and not any(m in k.upper() for m in _SECRET_ENV_MARKERS):
            keep[k] = os.environ[k]
    keep["ANONYMIZED_TELEMETRY"] = "false"
    keep["BROWSER_USE_TELEMETRY"] = "false"
    keep["BROWSER_USE_LOGGING_LEVEL"] = "error"
    return keep


class BrowserUseSubprocessAdapter:
    def __init__(self, config: BrowserUseConfig, *, allowed_hosts: list[str] | tuple[str, ...]):
        self.config = config
        self.allowed_hosts = list(allowed_hosts)
        self._last_proc_alive = False

    def _allowed_domains_for_bu(self) -> list[str]:
        # browser-use matches allowed_domains with optional wildcards.
        out: list[str] = []
        for h in self.allowed_hosts:
            out.append(h)
            out.append(f"*.{h}")
        return out

    def acquire(self, url: str, *, task: str = "", mission_id: str = "") -> dict:
        """Run one bounded agentic acquisition. Returns a normalized payload."""
        # Pre-flight domain policy (never launch the agent at a blocked host).
        dom = check_domain(url, allowed_hosts=self.allowed_hosts)
        if not dom.allowed:
            return self._degraded("BROWSER_USE_DOMAIN_BLOCKED", f"pre-flight blocked: {dom.reason}", url)

        req = {
            "url": url, "task": task,
            "allowed_domains": self._allowed_domains_for_bu(),
            "model": self.config.model, "ollama_host": self.config.ollama_host,
            "max_steps": self.config.max_steps,
            "model_timeout_sec": self.config.model_timeout_sec,
        }
        t0 = time.time()
        proc = None
        try:
            proc = subprocess.Popen(
                [self.config.isolated_python, self.config.runner_path],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=_child_env(), start_new_session=True, text=True,
            )
            self._last_proc_alive = True
            out, err = proc.communicate(input=json.dumps(req), timeout=self.config.max_runtime_sec)
        except subprocess.TimeoutExpired:
            self._kill_tree(proc)
            return self._degraded("BROWSER_USE_TIMEOUT",
                                  f"exceeded {self.config.max_runtime_sec}s", url,
                                  runtime=time.time() - t0)
        except Exception as e:
            self._kill_tree(proc)
            return self._degraded("BROWSER_USE_CRASH", f"{type(e).__name__}: {e}", url,
                                  runtime=time.time() - t0)
        finally:
            self._last_proc_alive = bool(proc and proc.poll() is None)

        runtime = time.time() - t0
        if proc.returncode not in (0, None):
            return self._degraded("BROWSER_USE_CRASH",
                                  f"exit={proc.returncode} {(err or '')[:200]}", url, runtime=runtime)

        payload = self._parse(out)
        if payload is None:
            return self._degraded("BROWSER_USE_INVALID_RESULT", (out or "")[:200], url, runtime=runtime)
        if payload.get("status") == "error":
            cat = payload.get("error_category", "")
            mapped = ("BROWSER_USE_MODEL_UNAVAILABLE" if cat == "model_unavailable"
                      else "BROWSER_USE_CRASH")
            return self._degraded(mapped, payload.get("message", ""), url, runtime=runtime)

        # Defense in depth: re-validate EVERY visited URL against domain policy.
        visited = payload.get("visited_urls") or []
        blocked = [u for u in visited if not check_domain(u, allowed_hosts=self.allowed_hosts).allowed]
        if blocked:
            return self._degraded("BROWSER_USE_DOMAIN_BLOCKED",
                                  f"agent navigated off-policy: {blocked[:3]}", url, runtime=runtime)

        payload["runtime_sec"] = round(runtime, 3)
        payload["driver"] = "BROWSER_USE"
        return payload

    def _parse(self, out: str) -> dict | None:
        if not out:
            return None
        # runner emits one JSON object; tolerate trailing log lines.
        for line in reversed(out.strip().splitlines()):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    return json.loads(line)
                except Exception:
                    continue
        try:
            return json.loads(out)
        except Exception:
            return None

    def _degraded(self, category: str, message: str, url: str, *, runtime: float = 0.0) -> dict:
        return {
            "status": "degraded", "error_category": category, "message": str(message)[:300],
            "final_url": url, "content": "", "visited_urls": [], "steps": 0,
            "driver": "BROWSER_USE", "runtime_sec": round(runtime, 3),
        }

    def _kill_tree(self, proc) -> None:
        if proc is None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        try:
            proc.wait(timeout=5)
        except Exception:
            pass

    def cleanup(self) -> dict:
        return {"closed": True, "subprocess_alive": self._last_proc_alive, "driver": "BROWSER_USE"}


class BrowserUseResearchProvider(BrowserResearchProvider):
    """browser-use behind the FROZEN provider contract (an escalation driver)."""

    def __init__(self, *, config: BrowserUseConfig, allowed_hosts, max_pages: int = 6,
                 max_runtime_sec: float = 120.0):
        self.adapter = BrowserUseSubprocessAdapter(config, allowed_hosts=allowed_hosts)
        self.max_pages = int(max_pages)
        self.max_runtime_sec = float(max_runtime_sec)
        self._pages_fetched = 0
        self._started = time.time()
        self._closed = False

    @property
    def pages_fetched(self) -> int:
        return self._pages_fetched

    def fetch(self, url: str, *, mission_id: str, actor: str = "user:owner",
              selector: str = "", timeout: int = 30) -> FetchedPage:
        if self._closed:
            raise RuntimeError("provider closed")
        if self._pages_fetched >= self.max_pages:
            return FetchedPage(url=url, final_origin="", title="", content="",
                               status="blocked", error_category="max_pages_exceeded")
        payload = self.adapter.acquire(url, mission_id=mission_id)
        self._pages_fetched += 1
        if payload.get("status") == "degraded":
            return FetchedPage(url=url, final_origin="", title="", content="",
                               status="failed", error_category=payload.get("error_category", ""))
        content = str(payload.get("content") or "")
        return FetchedPage(
            url=url,
            final_origin=f"https://{host_of(payload.get('final_url') or url)}",
            title=str(payload.get("title") or ""),
            content=content,
            status="succeeded",
            injection_hits=tuple(detect_prompt_injection(content)),
            retrieval_ts=time.time(),
        )

    def cleanup(self) -> dict:
        self._closed = True
        c = self.adapter.cleanup()
        c["pages_fetched"] = self._pages_fetched
        c["runtime_sec"] = round(time.time() - self._started, 3)
        return c
