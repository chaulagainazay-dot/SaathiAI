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


FIXED_ADDRESS = "https://macs-macbook-pro.tailbb1551.ts.net"


def get_mobile_link() -> dict:
    """Permanent phone-access URL via Tailscale (never changes)."""
    import os
    token = os.getenv("SAATHI_TOKEN", "")
    return {"mobile_link": f"{FIXED_ADDRESS}/#token={token}" if token else FIXED_ADDRESS,
            "note": "Permanent address — works anywhere as long as the phone's "
                    "Tailscale app is connected and the Mac is on."}


def applescript(script: str) -> dict:
    """Control any Mac app via AppleScript (Notes, Mail, Music, Finder, ...)."""
    p = subprocess.run(["osascript", "-e", script], capture_output=True,
                       text=True, timeout=60)
    if p.returncode != 0:
        return {"ok": False, "error": p.stderr.strip()}
    return {"ok": True, "output": p.stdout.strip()}
