"""M17.1 canonical live browser driver — real Chrome via CDP (loopback only).

This is the ONLY place a real browser is driven. It launches a system Chromium
headless with an ISOLATED temp profile bound to a bounded loopback debug port,
speaks the Chrome DevTools Protocol over a minimal stdlib websocket (no external
dependency, no browser install), and exposes navigate / dom / query / click /
fill / screenshot / close. It never reuses the user's normal profile, never
binds to a non-loopback interface, and shuts the browser down with the session.

Agents NEVER call this directly — the ComputerAdapter invokes it behind
ComputerActionIntent → ExecutionGateway. When no browser binary is present the
driver reports unavailable (dependency-blocked) and nothing is faked.

M17.24: this module is on the low-level driver allowlist. Production product
code outside the allowlist must not import LiveBrowserDriver (enforced by
``saathi.browser.guard.scan_repository``). Prefer GovernedBrowser for browser
family work; computer-agent live sessions remain gateway-routed via ComputerAdapter.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from dataclasses import dataclass

# candidate system browsers (Chromium family). No install performed.
_CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
]


def chrome_path() -> str | None:
    for p in _CHROME_PATHS:
        if p and os.path.exists(p):
            return p
    return None


def browser_available() -> dict:
    p = chrome_path()
    return {"available": bool(p), "path": p,
            "status": "available" if p else "dependency_blocked"}


# ── minimal CDP websocket client (stdlib only) ──────────────────────────────
class _WS:
    def __init__(self, url: str, timeout: float = 10.0):
        # ws://127.0.0.1:PORT/devtools/page/ID
        assert url.startswith("ws://")
        host_port, self.path = url[5:].split("/", 1)
        self.path = "/" + self.path
        self.host, port = host_port.split(":")
        self.port = int(port)
        self.sock = socket.create_connection((self.host, self.port), timeout=timeout)
        self.sock.settimeout(timeout)
        self._handshake()

    def _handshake(self):
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET {self.path} HTTP/1.1\r\nHost: {self.host}:{self.port}\r\n"
               f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.sock.recv(1024)
        if b"101" not in buf.split(b"\r\n")[0]:
            raise RuntimeError("CDP websocket handshake failed")

    def send(self, obj: dict):
        data = json.dumps(obj).encode()
        header = bytearray([0x81])           # FIN + text frame
        mask = os.urandom(4)
        n = len(data)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += n.to_bytes(2, "big")
        else:
            header.append(0x80 | 127)
            header += n.to_bytes(8, "big")
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.sock.sendall(bytes(header) + masked)

    def recv(self) -> dict:
        b1 = self._read(1)[0]
        b2 = self._read(1)[0]
        length = b2 & 0x7F
        if length == 126:
            length = int.from_bytes(self._read(2), "big")
        elif length == 127:
            length = int.from_bytes(self._read(8), "big")
        payload = self._read(length) if length else b""
        return json.loads(payload.decode()) if payload else {}

    def _read(self, n: int) -> bytes:
        out = b""
        while len(out) < n:
            chunk = self.sock.recv(n - len(out))
            if not chunk:
                raise ConnectionError("CDP socket closed")
            out += chunk
        return out

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


@dataclass
class BrowserEvidence:
    action: str
    ok: bool
    detail: dict


class LiveBrowserDriver:
    """Owns a Chrome process + CDP session. Confined + loopback-only."""

    def __init__(self, *, port: int = 0, profile_dir: str | None = None):
        self.path = chrome_path()
        self.port = port or _free_port()
        self.profile_dir = profile_dir or tempfile.mkdtemp(prefix="saathi-cdp-profile-")
        self.proc: subprocess.Popen | None = None
        self._ws: _WS | None = None
        self._msg_id = 0

    def available(self) -> bool:
        return bool(self.path)

    def launch(self, url: str = "about:blank") -> BrowserEvidence:
        if not self.path:
            return BrowserEvidence("launch", False, {"status": "dependency_blocked"})
        self.proc = subprocess.Popen(
            [self.path, "--headless=new", "--disable-gpu", "--no-first-run",
             "--no-default-browser-check",
             f"--remote-debugging-port={self.port}",
             "--remote-debugging-address=127.0.0.1",   # loopback ONLY
             f"--user-data-dir={self.profile_dir}",     # isolated profile
             url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # wait for the CDP endpoint
        ws_url = None
        for _ in range(50):
            try:
                data = json.load(urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/json", timeout=1))
                pages = [t for t in data if t.get("type") == "page"]
                if pages and pages[0].get("webSocketDebuggerUrl"):
                    ws_url = pages[0]["webSocketDebuggerUrl"]
                    break
            except Exception:
                time.sleep(0.1)
        if not ws_url:
            self.close()
            return BrowserEvidence("launch", False, {"status": "cdp_unavailable"})
        self._ws = _WS(ws_url)
        self._cmd("Page.enable")
        self._cmd("Runtime.enable")
        # CDP endpoint readiness ≠ document ready (esp. file:// on slower Linux runners).
        ready = self.wait_dom_ready(timeout=5.0)
        return BrowserEvidence("launch", True,
                               {"pid": self.proc.pid, "port": self.port,
                                "profile_isolated": True, "loopback_only": True,
                                "dom_ready": ready})

    def _cmd(self, method: str, params: dict | None = None) -> dict:
        self._msg_id += 1
        mid = self._msg_id
        self._ws.send({"id": mid, "method": method, "params": params or {}})
        # read until we get our id (skip events)
        for _ in range(200):
            msg = self._ws.recv()
            if msg.get("id") == mid:
                return msg.get("result", {})
        return {}

    def wait_dom_ready(self, timeout: float = 5.0) -> bool:
        """Bounded poll until document.readyState is complete (or interactive with body)."""
        deadline = time.monotonic() + float(timeout)
        while time.monotonic() < deadline:
            r = self._cmd(
                "Runtime.evaluate",
                {
                    "expression": (
                        "({state: document.readyState, "
                        "hasBody: !!document.body, "
                        "ready: document.readyState === 'complete' || "
                        "(document.readyState === 'interactive' && !!document.body)})"
                    ),
                    "returnByValue": True,
                },
            )
            val = (r.get("result") or {}).get("value") or {}
            if isinstance(val, dict) and val.get("ready"):
                return True
            time.sleep(0.05)
        return False

    def wait_for_selector(self, selector: str, timeout: float = 5.0) -> bool:
        """Bounded poll until querySelector matches. No unbounded retry."""
        deadline = time.monotonic() + float(timeout)
        while time.monotonic() < deadline:
            if self.query_exists(selector):
                return True
            time.sleep(0.05)
        return False

    def navigate(self, url: str) -> BrowserEvidence:
        self._cmd("Page.navigate", {"url": url})
        ready = self.wait_dom_ready(timeout=5.0)
        cur = self.current_url()
        return BrowserEvidence("navigate", True, {"url": cur, "dom_ready": ready})

    def current_url(self) -> str:
        r = self._cmd("Runtime.evaluate",
                      {"expression": "location.href", "returnByValue": True})
        return (r.get("result") or {}).get("value", "")

    def title(self) -> str:
        r = self._cmd("Runtime.evaluate",
                      {"expression": "document.title", "returnByValue": True})
        return (r.get("result") or {}).get("value", "")

    def dom_text(self, selector: str = "body") -> str:
        expr = f"(document.querySelector({json.dumps(selector)})||{{}}).innerText||''"
        r = self._cmd("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        return (r.get("result") or {}).get("value", "")

    def query_exists(self, selector: str) -> bool:
        expr = f"!!document.querySelector({json.dumps(selector)})"
        r = self._cmd("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        return bool((r.get("result") or {}).get("value"))

    def click(self, selector: str) -> BrowserEvidence:
        expr = (f"(function(){{var e=document.querySelector({json.dumps(selector)});"
                f"if(!e)return false;e.click();return true;}})()")
        r = self._cmd("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        ok = bool((r.get("result") or {}).get("value"))
        return BrowserEvidence("click", ok, {"selector": selector})

    def fill(self, selector: str, value: str) -> BrowserEvidence:
        # NOTE: caller must ensure the field is NOT sensitive (policy gate upstream)
        expr = (f"(function(){{var e=document.querySelector({json.dumps(selector)});"
                f"if(!e)return false;e.value={json.dumps(value)};"
                f"e.dispatchEvent(new Event('input',{{bubbles:true}}));return true;}})()")
        r = self._cmd("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        ok = bool((r.get("result") or {}).get("value"))
        return BrowserEvidence("fill", ok, {"selector": selector})

    def screenshot(self, out_path: str) -> BrowserEvidence:
        r = self._cmd("Page.captureScreenshot", {"format": "png"})
        data = r.get("data")
        if not data:
            return BrowserEvidence("screenshot", False, {})
        raw = base64.b64decode(data)
        with open(out_path, "wb") as f:
            f.write(raw)
        return BrowserEvidence("screenshot", True,
                               {"path": out_path, "bytes": len(raw)})

    def close(self) -> BrowserEvidence:
        if self._ws:
            self._ws.close(); self._ws = None
        exited = True
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()
                exited = False
        # clean the isolated profile (never committed)
        shutil.rmtree(self.profile_dir, ignore_errors=True)
        return BrowserEvidence("close", True, {"process_exited": exited,
                                               "profile_cleaned": True})


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port
