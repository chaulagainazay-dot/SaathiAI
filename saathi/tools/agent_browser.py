"""agent_browser.py — agent-browser CLI integration for Baadar.

Wraps https://github.com/vercel-labs/agent-browser so Baadar can control
a headless Chrome browser: navigate, click, type, screenshot, extract text,
run JS, and do full AI-driven browser control.
"""
from __future__ import annotations
import json
import subprocess
import shutil

_BIN = shutil.which("agent-browser") or "/opt/homebrew/bin/agent-browser"


def _run(*args: str, timeout: int = 30) -> dict:
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


# ── Navigation ────────────────────────────────────────────────────────────────

def ab_open(url: str = "") -> dict:
    """Open browser and navigate to URL (leave url blank to just launch)."""
    return _run("open", url) if url else _run("open")

def ab_goto(url: str) -> dict:
    """Navigate to a URL in the running browser session."""
    return _run("open", url)

def ab_close() -> dict:
    """Close the current browser session."""
    return _run("close")


# ── Reading ───────────────────────────────────────────────────────────────────

def ab_snapshot() -> dict:
    """Get accessibility tree — best structured view for AI reasoning about a page."""
    return _run("snapshot", timeout=15)

def ab_get_text(selector: str) -> dict:
    """Get visible text of element matching CSS selector."""
    return _run("get", "text", selector)

def ab_get_url() -> dict:
    """Get current page URL."""
    return _run("get", "url")

def ab_get_title() -> dict:
    """Get current page title."""
    return _run("get", "title")

def ab_screenshot(path: str = "") -> dict:
    """Take a screenshot. Optionally specify save path."""
    return _run("screenshot", path) if path else _run("screenshot")

def ab_eval(js: str) -> dict:
    """Execute JavaScript on the page and return result."""
    return _run("eval", js, timeout=20)


# ── Interaction ───────────────────────────────────────────────────────────────

def ab_click(selector: str) -> dict:
    """Click element by CSS selector."""
    return _run("click", selector)

def ab_fill(selector: str, text: str) -> dict:
    """Clear an input field and fill it with text."""
    return _run("fill", selector, text)

def ab_type(selector: str, text: str) -> dict:
    """Type text into element (without clearing first)."""
    return _run("type", selector, text)

def ab_press(key: str) -> dict:
    """Press a key: Enter, Tab, Escape, Control+a, etc."""
    return _run("press", key)

def ab_scroll(direction: str, pixels: str = "300") -> dict:
    """Scroll page. direction: up | down | left | right"""
    return _run("scroll", direction, pixels)

def ab_wait(selector_or_ms: str) -> dict:
    """Wait for an element to appear, or wait N milliseconds."""
    return _run("wait", selector_or_ms, timeout=20)


# ── Semantic find ─────────────────────────────────────────────────────────────

def ab_find_text(text: str, action: str = "click") -> dict:
    """Find element by visible text and perform action (click / text / hover)."""
    return _run("find", "text", text, action)

def ab_find_role(role: str, name: str = "", action: str = "click") -> dict:
    """Find element by ARIA role (button/link/input) optionally filtered by name."""
    args = ["find", "role", role, action]
    if name:
        args += ["--name", name]
    return _run(*args)


# ── Batch & AI ────────────────────────────────────────────────────────────────

def ab_batch(commands: list[str]) -> dict:
    """Run multiple browser commands in one fast call.
    commands: e.g. ["open https://example.com", "snapshot", "screenshot"]
    """
    if not commands:
        return {"error": "empty commands list"}
    return _run("batch", *commands, timeout=60)

def ab_ai_chat(instruction: str) -> dict:
    """Control browser with natural language via agent-browser's built-in AI.
    Example: 'Go to google.com, search IELTS tips, take a screenshot.'
    """
    return _run("chat", instruction, timeout=120)


# ── Status ────────────────────────────────────────────────────────────────────

def ab_status() -> dict:
    """Check agent-browser health: Chrome, daemon, config."""
    return _run("doctor", "--json", timeout=10)
