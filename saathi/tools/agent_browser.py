"""agent_browser.py — agent-browser CLI integration (M17.24 governed).

Raw subprocess control of headless Chrome is **disabled** for production tool
dispatch. Legitimate browser work must enter through:

    GovernedBrowser.execute → ExecutionGateway → BrowserAdapter

Emergency local override (never production default)::

    SAATHI_ALLOW_RAW_BROWSER=1
"""
from __future__ import annotations

import json
import shutil
import subprocess

from saathi.browser.guard import deny_raw_production_dispatch, raw_browser_env_enabled

_BIN = shutil.which("agent-browser") or "/opt/homebrew/bin/agent-browser"


def _run(*args: str, timeout: int = 30) -> dict:
    """Low-level CLI runner — blocked unless raw env override is set."""
    if not raw_browser_env_enabled():
        return deny_raw_production_dispatch(
            source="saathi.tools.agent_browser._run",
            action=" ".join(args)[:80],
        )
    cmd = [_BIN] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = r.stdout.strip()
        err = r.stderr.strip()
        if r.returncode != 0:
            return {"error": err or f"exit code {r.returncode}", "cmd": " ".join(args)}
        try:
            return {"ok": True, "result": json.loads(out)}
        except Exception:
            return {"ok": True, "result": out}
    except subprocess.TimeoutExpired:
        return {"error": f"timeout after {timeout}s"}
    except FileNotFoundError:
        return {"error": "agent-browser not installed — run: npm install -g agent-browser && agent-browser install"}
    except Exception as e:
        return {"error": str(e)}


def _governed(action: str, *, url: str = "", selector: str = "",
              payload: dict | None = None, actor: str = "agent:tool") -> dict:
    """Delegate to canonical GovernedBrowser boundary."""
    try:
        from saathi.browser.governed import default_governed_browser
        gb = default_governed_browser()
        rec = gb.execute(
            action=action,
            url=url,
            selector=selector,
            payload=payload,
            actor=actor,
            request_source="agent",
            mission_id="agent_browser",
            mission_run_id=f"ab-{action}",
            environment="dev",
        )
        return {
            "ok": rec.status == "succeeded",
            "status": rec.status,
            "execution_id": rec.execution_id,
            "summary": rec.result_summary,
            "failure_category": rec.failure_category,
            "governed": True,
        }
    except Exception as e:
        return {"error": "governance_error", "message": str(e)[:200], "governed": True}


# ── Navigation ────────────────────────────────────────────────────────────────

def ab_open(url: str = "") -> dict:
    """Open browser and navigate to URL via governed gateway."""
    if not url:
        return deny_raw_production_dispatch(source="ab_open", action="open")
    return _governed("navigate", url=url)

def ab_goto(url: str) -> dict:
    """Navigate to a URL via governed gateway."""
    return _governed("navigate", url=url)

def ab_close() -> dict:
    """Close is a session lifecycle op — recorded as governed no-op fail-closed."""
    return {
        "ok": True,
        "result": "session_close_acknowledged",
        "governed": True,
        "note": "raw agent-browser close disabled; no live driver session in production path",
    }


# ── Reading ───────────────────────────────────────────────────────────────────

def ab_snapshot() -> dict:
    return deny_raw_production_dispatch(source="ab_snapshot", action="snapshot")

def ab_get_text(selector: str) -> dict:
    return deny_raw_production_dispatch(source="ab_get_text", action=f"get_text:{selector}")

def ab_get_url() -> dict:
    return deny_raw_production_dispatch(source="ab_get_url", action="get_url")

def ab_get_title() -> dict:
    return deny_raw_production_dispatch(source="ab_get_title", action="get_title")

def ab_screenshot(path: str = "") -> dict:
    # Without URL, cannot form a governed intent — fail closed
    if path and path.startswith("http"):
        return _governed("screenshot", url=path)
    return deny_raw_production_dispatch(source="ab_screenshot", action="screenshot")

def ab_eval(js: str) -> dict:
    """eval_js is a prohibited browser action — always fail closed."""
    return _governed("eval_js", url="https://example.com/", payload={"js_digest": "redacted"})


# ── Interaction ───────────────────────────────────────────────────────────────

def _interactive_act(action: str, **kwargs) -> dict:
    """M17.25: interactive tools use governed InteractiveBrowser sessions."""
    try:
        from saathi.browser.interactive import default_interactive_browser
        from saathi.browser.gov_session import SessionError
        ib = default_interactive_browser()
        session_id = kwargs.pop("session_id", "") or ""
        actor = kwargs.pop("actor", "agent:tool")
        if not session_id:
            # ephemeral governed session for agent tools (read_only + low_interactive)
            sess = ib.open_session(
                actor_id=actor,
                mission_id="agent_browser",
                mission_run_id=f"ab-{action}",
                request_source="agent",
                allowed_action_classes=["read_only", "low_interactive", "sensitive_input"],
                url=kwargs.get("url") or "https://example.com/",
            )
            session_id = sess.session_id
        res = ib.act(
            session_id=session_id,
            action=action,
            actor_id=actor,
            selector=kwargs.get("selector") or "",
            text=kwargs.get("text") or "",
            url=kwargs.get("url") or "",
            idempotency_key=kwargs.get("idempotency_key") or "",
            approval_id=kwargs.get("approval_id") or "",
        )
        return {**res.as_dict(), "governed": True, "interactive": True}
    except Exception as e:
        return {"error": "interactive_governance_error", "message": str(e)[:200],
                "governed": True}


def ab_click(selector: str, **kwargs) -> dict:
    return _interactive_act("click", selector=selector, **kwargs)

def ab_fill(selector: str, text: str, **kwargs) -> dict:
    return _interactive_act("fill", selector=selector, text=text, **kwargs)

def ab_type(selector: str, text: str, **kwargs) -> dict:
    return _interactive_act("type", selector=selector, text=text, **kwargs)

def ab_press(key: str) -> dict:
    return deny_raw_production_dispatch(source="ab_press", action=f"press:{key}")

def ab_scroll(direction: str, pixels: str = "300") -> dict:
    return deny_raw_production_dispatch(source="ab_scroll", action=f"scroll:{direction}")

def ab_wait(selector_or_ms: str) -> dict:
    return deny_raw_production_dispatch(source="ab_wait", action=f"wait:{selector_or_ms}")


# ── Semantic find ─────────────────────────────────────────────────────────────

def ab_find_text(text: str, action: str = "click") -> dict:
    return deny_raw_production_dispatch(source="ab_find_text", action=f"find:{text}")

def ab_find_role(role: str, name: str = "", action: str = "click") -> dict:
    return deny_raw_production_dispatch(source="ab_find_role", action=f"role:{role}")


# ── Batch & AI ────────────────────────────────────────────────────────────────

def ab_batch(commands: list) -> dict:
    return deny_raw_production_dispatch(source="ab_batch", action="batch")

def ab_ai_chat(instruction: str) -> dict:
    return deny_raw_production_dispatch(source="ab_ai_chat", action="ai_chat")

def ab_status() -> dict:
    return {
        "ok": True,
        "governed": True,
        "raw_enabled": raw_browser_env_enabled(),
        "bin": _BIN if raw_browser_env_enabled() else None,
        "message": "agent-browser tools require GovernedBrowser; raw CLI disabled by default",
    }
