"""Browser posting — social compose via local browser (M17.24 governed).

Historical path drove Brave with AppleScript after voice approval. M17.24
disables raw AppleScript / open -a browser control unless emergency override
is set. Callers must use GovernedBrowser for any automated browser side effect.
"""
from __future__ import annotations

import subprocess
import time

from saathi.browser.guard import deny_raw_production_dispatch, raw_browser_env_enabled

BROWSER = "Brave Browser"

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


def post(platform: str, content: str, title: str = "", *,
         actor: str = "user:system", approval_id: str = "") -> dict:
    """Post via browser. Production path is fail-closed without raw override.

    When SAATHI_ALLOW_RAW_BROWSER=1, legacy AppleScript path remains for local
    operator use after explicit approval_id is present.
    """
    platform = platform.lower()
    if platform not in COMPOSE_URL:
        return {"error": f"unsupported platform: {platform}",
                "supported": list(COMPOSE_URL)}

    # Always record a governed intent for auditability
    try:
        from saathi.browser.governed import default_governed_browser
        rec = default_governed_browser().execute(
            action="submit",
            url=COMPOSE_URL[platform],
            actor=actor,
            approval_id=approval_id,
            approval_pre_resolved=bool(approval_id),
            request_source="tool",
            mission_id="social_post",
            mission_run_id=f"social-{platform}",
            environment="dev",
            payload={"platform": platform, "content_digest": "redacted"},
        )
        if rec.status not in ("succeeded", "approval_required") and not approval_id:
            return {
                "error": "governance_denied",
                "status": rec.status,
                "execution_id": rec.execution_id,
                "message": rec.result_summary or "browser post requires approval",
                "governed": True,
            }
        if rec.status == "approval_required":
            return {
                "error": "approval_required",
                "execution_id": rec.execution_id,
                "message": "High-risk social post requires digest-bound approval",
                "governed": True,
            }
    except Exception as e:
        return {"error": "governance_error", "message": str(e)[:200], "governed": True}

    if not raw_browser_env_enabled():
        return {
            **deny_raw_production_dispatch(source="saathi.tools.browser.post",
                                           action=f"post:{platform}"),
            "note": "Governed intent recorded; raw AppleScript actuation disabled. "
                    "Set SAATHI_ALLOW_RAW_BROWSER=1 for local operator fallback.",
            "platform": platform,
        }

    body = (f"{title}\n\n{content}" if title and platform != "facebook" else content)
    _set_clipboard(body)

    subprocess.run(["open", "-a", BROWSER, COMPOSE_URL[platform]], timeout=15)
    time.sleep(4)

    ok, err = _osa(f'tell application "{BROWSER}" to activate')
    time.sleep(1)

    if platform == "linkedin":
        steps = ('tell application "System Events"\n'
                 ' keystroke "v" using command down\n'
                 ' delay 1.5\n'
                 ' keystroke return using command down\n'
                 'end tell')
    else:
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
                    "Cmd+Return. Check the browser to confirm it went live.",
            "raw_override": True}
