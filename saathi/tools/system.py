"""Full-access system tools — shell, file writing, AppleScript app control.

M49.3: freeform shell is PROHIBITED at runtime. Use allowlisted command
manifests via ExecutionGateway (m49.allowlisted_command). AppleScript and
arbitrary write_file remain deferred/privileged and are blocked by legacy
policy at execute_tool for deferred tools; direct imports also fail closed
for freeform shell.
"""
import subprocess
from pathlib import Path

HOME = Path.home()

# absolute no-gos even with confirmation — typo here = dead Mac
CATASTROPHIC = ("rm -rf /", "rm -rf ~", "rm -rf $HOME", "mkfs", "diskutil eraseDisk",
                "dd if=", "> /dev/", ":(){", "chmod -R 777 /")


def run_shell(command: str, timeout_sec: int = 60) -> dict:
    """M49.3: freeform shell execution is blocked.

    Callers must use ``m49.allowlisted_command`` through ExecutionGateway with
    a code-owned command_id. Arbitrary shell invocation is never used.
    """
    return {
        "error": "freeform_shell_blocked",
        "blocked": True,
        "reason": (
            "M49.3: freeform shell / arbitrary command strings are prohibited. "
            "Use allowlisted command manifests via ExecutionGateway "
            "(tool_id=m49.allowlisted_command, command_id=...)."
        ),
        "message": (
            "Freeform shell blocked. Allowed path: "
            "ExecutionGateway.execute_registered_tool("
            "tool_id='m49.allowlisted_command', arguments={'command_id': '...'})"
        ),
        "outcome_class": "PROHIBITED",
        "shell": False,
        "command_rejected": True,
        "timeout_sec_ignored": timeout_sec,
        "command_preview": str(command)[:80] if command else "",
    }


def write_file(path: str, content: str, append: bool = False) -> dict:
    """Create or edit a file under Ajay's home folder.

    M49.3: deferred from generic agent runtime (legacy policy). Direct call
    still validates home root for compatibility with tests that import this
    helper intentionally.
    """
    p = Path(path).expanduser().resolve()
    if not str(p).startswith(str(HOME)):
        return {"error": "outside_home", "note": "Can only write inside your home folder."}
    p.parent.mkdir(parents=True, exist_ok=True)
    existed = p.exists()
    with open(p, "a" if append else "w") as f:
        f.write(content)
    return {"written": str(p), "bytes": len(content.encode()),
            "mode": "appended" if append else ("overwrote" if existed else "created")}


TAILSCALE_ADDRESS = "https://macs-macbook-pro.tailbb1551.ts.net"


def get_mobile_link() -> dict:
    """Phone-access URL. Prefers the public Cloudflare tunnel (works on any phone,
    no VPN); falls back to the Tailscale address."""
    import os
    import re
    token = os.getenv("SAATHI_TOKEN", "")
    # Never return raw token in M49.3 evidence-facing path — mask presence only
    suffix = "/#token=***" if token else ""
    log = HOME / "SaathiAI" / "data" / "tunnel.log"
    if log.exists():
        urls = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", log.read_text())
        if urls:
            return {"mobile_link": urls[-1] + suffix,
                    "type": "public (no VPN needed)",
                    "note": "Works on any phone over normal internet. URL changes if "
                            "the Mac reboots — just ask me again for the new one.",
                    "token_embedded": bool(token)}
    return {"mobile_link": TAILSCALE_ADDRESS + suffix,
            "type": "tailscale (needs VPN app)",
            "note": "Cloudflare tunnel not running; this needs Tailscale on the phone.",
            "token_embedded": bool(token)}


def applescript(script: str) -> dict:
    """Control any Mac app via AppleScript.

    M49.3: freeform AppleScript is treated as privileged deferred runtime.
    Direct invocation is blocked to prevent arbitrary script execution.
    """
    return {
        "error": "freeform_shell_blocked",
        "blocked": True,
        "ok": False,
        "reason": "M49.3: freeform AppleScript is prohibited at runtime (deferred privileged Mac).",
        "outcome_class": "PROHIBITED",
        "script_preview": str(script)[:80] if script else "",
    }
