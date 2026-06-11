"""MacBook control: open apps, run Shortcuts, type text. Uses macOS built-ins only."""
import subprocess


def _run(cmd: list[str]) -> dict:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if p.returncode != 0:
        return {"ok": False, "error": p.stderr.strip()}
    return {"ok": True, "output": p.stdout.strip()}


def open_app(app_name: str) -> dict:
    return _run(["open", "-a", app_name])


def run_shortcut(shortcut_name: str, input_text: str = "") -> dict:
    cmd = ["shortcuts", "run", shortcut_name]
    if input_text:
        p = subprocess.run(cmd, input=input_text, capture_output=True, text=True, timeout=120)
    else:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        return {"ok": False, "error": p.stderr.strip()}
    return {"ok": True, "output": p.stdout.strip()}


def type_text(text: str) -> dict:
    # AppleScript keystroke into frontmost app (dictation-style)
    safe = text.replace("\\", "\\\\").replace('"', '\\"')
    script = f'tell application "System Events" to keystroke "{safe}"'
    return _run(["osascript", "-e", script])
