"""Browser posting — post to Facebook & LinkedIn through the logged-in browser.

No API keys, no developer apps: it drives the browser where Ajay is already
signed in. Flow: open the compose box → paste the approved text → submit with
Cmd+Return (the post shortcut on both sites). Always called only AFTER Ajay has
approved the exact text by voice.

Needs macOS Accessibility permission for keystrokes (guided once).
"""
import subprocess
import time

BROWSER = "Brave Browser"

# Compose surfaces. LinkedIn has a direct share-box URL; Facebook opens the
# composer on the home feed (Ajay clicks once if it isn't focused).
COMPOSE_URL = {
    "linkedin": "https://www.linkedin.com/feed/?shareActive=true&mini=true",
    "facebook": "https://www.facebook.com/",
}


def _osa(script: str) -> tuple[bool, str]:
    p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True,
                       timeout=30)
    return p.returncode == 0, (p.stderr or p.stdout).strip()


def _set_clipboard(text: str):
    subprocess.run(["pbcopy"], input=text.encode(), timeout=10)


def post(platform: str, content: str, title: str = "") -> dict:
    platform = platform.lower()
    if platform not in COMPOSE_URL:
        return {"error": f"unsupported platform: {platform}",
                "supported": list(COMPOSE_URL)}

    body = (f"{title}\n\n{content}" if title and platform != "facebook" else content)
    _set_clipboard(body)

    # open the compose page in the browser where Ajay is logged in
    subprocess.run(["open", "-a", BROWSER, COMPOSE_URL[platform]], timeout=15)
    time.sleep(4)  # let the page + compose box load

    # bring browser to front, click into the compose area, paste, submit
    ok, err = _osa(f'tell application "{BROWSER}" to activate')
    time.sleep(1)

    if platform == "linkedin":
        # share box is already focused; paste then Cmd+Return to post
        steps = ('tell application "System Events"\n'
                 ' keystroke "v" using command down\n'
                 ' delay 1.5\n'
                 ' keystroke return using command down\n'
                 'end tell')
    else:  # facebook — focus composer, paste, submit
        steps = ('tell application "System Events"\n'
                 ' keystroke "v" using command down\n'
                 ' delay 1.5\n'
                 ' keystroke return using command down\n'
                 'end tell')

    ok, err = _osa(steps)
    if not ok:
        if "not allowed" in err.lower() or "assistive" in err.lower():
            return {"error": "accessibility_permission_needed",
                    "message": "Grant Accessibility to SaathiAI's python once: System "
                               "Settings → Privacy & Security → Accessibility. The post "
                               "text is already on the clipboard and the page is open — "
                               "Ajay can paste with Cmd+V and click Post manually.",
                    "fallback": "pasted_to_clipboard"}
        return {"error": "keystroke_failed", "detail": err,
                "note": "Text is on the clipboard and the compose page is open."}

    return {"posted": True, "platform": platform,
            "note": "Opened the compose box, pasted your text, and submitted with "
                    "Cmd+Return. Check the browser to confirm it went live."}
