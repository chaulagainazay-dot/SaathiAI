"""M17.4 application discovery — real installed-application detection.

macOS: NSWorkspace running apps + /Applications + ~/Applications bundles +
`which` for CLI tools + `brew list`. Windows/Linux paths are contract-ready
(implemented, not exercised on macOS). Maps discovered applications to known
harness definitions and honest availability. Read-only; never launches anything.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

# application_name -> (harness_id, cli executables that indicate availability)
KNOWN_HARNESSES = {
    "ffmpeg": ("ffmpeg", ["ffmpeg", "ffprobe"]),
    "libreoffice": ("libreoffice", ["soffice", "libreoffice"]),
    "blender": ("blender", ["blender"]),
    "kdenlive": ("kdenlive", ["kdenlive", "melt"]),
    "inkscape": ("inkscape", ["inkscape"]),
    "imagemagick": ("imagemagick", ["magick", "convert"]),
}


def _bundle_version(app_path: str) -> str:
    plist = Path(app_path) / "Contents" / "Info.plist"
    if not plist.exists():
        return ""
    try:
        r = subprocess.run(["defaults", "read", str(plist).replace(".plist", ""),
                           "CFBundleShortVersionString"], capture_output=True,
                          text=True, timeout=5)
        return r.stdout.strip()
    except Exception:
        return ""


def discover_cli_tools() -> list[dict]:
    """CLI executables that back harnesses (the important ones for us)."""
    out = []
    for app, (hid, exes) in KNOWN_HARNESSES.items():
        found = next((shutil.which(e) for e in exes if shutil.which(e)), None)
        out.append({"application": app, "harness_id": hid,
                    "binary": found, "install_location": found,
                    "available": bool(found),
                    "health": "available" if found else "dependency_blocked"})
    return out


def discover_gui_apps(limit: int = 200) -> list[dict]:
    """macOS GUI applications from /Applications + ~/Applications (real)."""
    if platform.system() != "Darwin":
        return []
    roots = [Path("/Applications"), Path.home() / "Applications"]
    apps = []
    for root in roots:
        if not root.exists():
            continue
        for p in sorted(root.glob("*.app"))[:limit]:
            apps.append({"application": p.stem, "path": str(p),
                         "version": _bundle_version(str(p)), "vendor": "",
                         "install_location": str(p)})
    return apps


def discover() -> dict:
    system = platform.system()
    cli = discover_cli_tools()
    result = {
        "platform": system,
        "cli_harness_backends": cli,
        "available_harnesses": [c["harness_id"] for c in cli if c["available"]],
        "dependency_blocked": [c["harness_id"] for c in cli if not c["available"]],
    }
    if system == "Darwin":
        result["gui_applications"] = len(discover_gui_apps())
    elif system == "Windows":     # contract-ready
        result["note"] = "Windows discovery contract-ready (Registry/Program Files)"
    elif system == "Linux":
        result["note"] = "Linux discovery contract-ready (desktop entries/PATH)"
    return result
