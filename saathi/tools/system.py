"""Full-access system tools — shell, file writing, AppleScript app control.

All privileged (Ajay's verified voice only). The persona additionally requires
spoken confirmation before destructive actions; this module hard-blocks only
the catastrophic ones.
"""
import subprocess
from pathlib import Path

HOME = Path.home()

# absolute no-gos even with confirmation — typo here = dead Mac
CATASTROPHIC = ("rm -rf /", "rm -rf ~", "rm -rf $HOME", "mkfs", "diskutil eraseDisk",
                "dd if=", "> /dev/", ":(){", "chmod -R 777 /")


def run_shell(command: str, timeout_sec: int = 60) -> dict:
    """Run a shell command and return its output."""
    flat = " ".join(command.split())
    if any(bad in flat for bad in CATASTROPHIC):
        return {"blocked": True,
                "reason": "This command could destroy the system — refused."}
    p = subprocess.run(command, shell=True, capture_output=True, text=True,
                       timeout=min(timeout_sec, 300), cwd=str(HOME))
    out = (p.stdout or "")[-4000:]
    err = (p.stderr or "")[-2000:]
    return {"exit_code": p.returncode, "stdout": out, "stderr": err}


def write_file(path: str, content: str, append: bool = False) -> dict:
    """Create or edit a file under Ajay's home folder."""
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
    suffix = f"/#token={token}" if token else ""
    log = HOME / "SaathiAI" / "data" / "tunnel.log"
    if log.exists():
        urls = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", log.read_text())
        if urls:
            return {"mobile_link": urls[-1] + suffix,
                    "type": "public (no VPN needed)",
                    "note": "Works on any phone over normal internet. URL changes if "
                            "the Mac reboots — just ask me again for the new one."}
    return {"mobile_link": TAILSCALE_ADDRESS + suffix,
            "type": "tailscale (needs VPN app)",
            "note": "Cloudflare tunnel not running; this needs Tailscale on the phone."}


def applescript(script: str) -> dict:
    """Control any Mac app via AppleScript (Notes, Mail, Music, Finder, ...)."""
    p = subprocess.run(["osascript", "-e", script], capture_output=True,
                       text=True, timeout=60)
    if p.returncode != 0:
        return {"ok": False, "error": p.stderr.strip()}
    return {"ok": True, "output": p.stdout.strip()}
