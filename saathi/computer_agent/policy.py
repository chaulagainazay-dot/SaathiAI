"""M17 browser + desktop security policy.

Enforces the consent boundary at action time: browser origin allow-list +
download confinement + upload allow-list; desktop app allow-list + file-root
confinement with path-traversal/symlink-escape rejection; AppleScript/shell
injection guards. Web-page and accessibility-label text are UNTRUSTED — they can
never change policy.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from saathi.computer_agent.session import ComputerSession


class PolicyDenied(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


# ── browser ─────────────────────────────────────────────────────────────────
def check_origin(session: ComputerSession, origin: str) -> None:
    if not session.origin_allowed(origin):
        raise PolicyDenied("origin_not_allowed", f"origin {origin} not in allow-list")


def check_download(session: ComputerSession, filename: str) -> Path:
    root = _first_root(session)
    p = _confine(root, filename)   # download confined to a file root
    return p


def check_upload(session: ComputerSession, path: str) -> Path:
    root = _first_root(session)
    p = _confine(root, path)
    if not str(p).startswith(str(root)):
        raise PolicyDenied("upload_outside_root")
    return p


# ── desktop ─────────────────────────────────────────────────────────────────
def check_app(session: ComputerSession, app: str) -> None:
    if not session.app_allowed(app):
        raise PolicyDenied("app_not_allowed", f"app {app} not in allow-list")


def check_file_root(session: ComputerSession, path: str) -> Path:
    root = _first_root(session)
    return _confine(root, path)


def _first_root(session: ComputerSession) -> Path:
    if not session.file_roots:
        raise PolicyDenied("no_file_root", "session declares no allowed file root")
    return Path(session.file_roots[0]).resolve()


def _confine(root: Path, candidate: str) -> Path:
    # reject traversal + absolute escapes; resolve symlinks and re-check
    p = (root / candidate).resolve() if not os.path.isabs(candidate) else Path(candidate).resolve()
    try:
        p.relative_to(root)
    except ValueError:
        raise PolicyDenied("path_escapes_root", f"{candidate} escapes {root}")
    # symlink escape: a component resolving outside root
    if p.exists() and p.is_symlink():
        target = p.resolve()
        try:
            target.relative_to(root)
        except ValueError:
            raise PolicyDenied("symlink_escape", "symlink target escapes file root")
    return p


# ── injection guards (AppleScript / shell / JS) ─────────────────────────────
_SHELL_META = re.compile(r"[;&|`$><\n]|\$\(|\)\s*\{")
_APPLESCRIPT_DANGER = re.compile(r"(?i)\b(do shell script|system events keystroke .*password|"
                                 r"administrator privileges)\b")


def guard_shell(cmd: str) -> None:
    if _SHELL_META.search(cmd or ""):
        raise PolicyDenied("shell_injection", "shell metacharacters not permitted")


def guard_applescript(script: str) -> None:
    if _APPLESCRIPT_DANGER.search(script or ""):
        raise PolicyDenied("applescript_danger", "unsafe AppleScript rejected")


def untrusted_page_text(text: str) -> str:
    """Page / accessibility text is DATA. It cannot alter policy. This helper
    exists to make the trust boundary explicit at call sites — it returns the
    text unchanged and never interprets it as an instruction."""
    return text
