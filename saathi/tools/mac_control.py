"""MacBook control: open apps, run Shortcuts, type text. Uses macOS built-ins only."""
import subprocess


def _run(cmd: list[str]) -> dict:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if p.returncode != 0:
        return {"ok": False, "error": p.stderr.strip()}
    return {"ok": True, "output": p.stdout.strip()}


def open_app(app_name: str) -> dict:
    return _run(["open", "-a", app_name])


def close_app(app_name: str) -> dict:
    """Quit an application by name (fuzzy-matches what's actually running)."""
    # find the best-matching running app so "cloud code" → "Claude" etc. works
    running = subprocess.run(
        ["osascript", "-e",
         'tell application "System Events" to get name of every process whose background only is false'],
        capture_output=True, text=True, timeout=15).stdout
    names = [n.strip() for n in running.split(",") if n.strip()]
    want = app_name.lower().replace(" ", "")
    match = next((n for n in names if want in n.lower().replace(" ", "")
                  or n.lower().replace(" ", "") in want), None)
    target = match or app_name
    r = _run(["osascript", "-e", f'tell application "{target}" to quit'])
    if r["ok"]:
        return {"ok": True, "closed": target}
    return {"ok": False, "error": r["error"], "running_apps": names}


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
