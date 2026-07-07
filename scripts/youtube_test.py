#!/usr/bin/env python3
"""Local YouTube upload test — drives real Chrome on this Mac (no VM/queue).

  1) one-time login:   .venv/bin/python scripts/youtube_test.py login
  2) publish a clip:   .venv/bin/python scripts/youtube_test.py publish ~/clip.mp4 "My Title" Unlisted

`login` opens the ajay/youtube Chrome profile so you can sign in once; the
profile persists. `publish` runs the YouTubeUploadWorkflow and prints the step
timeline — if a selector is wrong, you'll see exactly which step failed.
"""
import json
import os
import sys

sys.path.insert(0, os.path.expanduser("~/SaathiAI"))

from saathi.infrastructure.human_browser import ChromeBackend, ProfileStore  # noqa: E402
from saathi.infrastructure.human_browser.primitives import BrowserPrimitives  # noqa: E402
from saathi.infrastructure.human_browser.workflows import YouTubeUploadWorkflow  # noqa: E402

PROFILE = "ajay/youtube"


def _backend():
    return ChromeBackend(ProfileStore(), headless=False, channel="chrome")


def login(timeout_min=8):
    """Open Chrome and WAIT until you're actually signed in (auto-detected), then
    save. No 'press Enter' — just log in; the script notices and closes itself."""
    import time
    from playwright.sync_api import sync_playwright
    be = _backend()
    with sync_playwright() as pw:
        ctx = be._context(pw, PROFILE)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.youtube.com/account", wait_until="domcontentloaded")
        print("\n>>> A Chrome window opened. SIGN INTO YOUTUBE there (your Google account).")
        print(">>> Do NOT touch this terminal — I'll detect the login automatically.\n")
        deadline = time.time() + timeout_min * 60
        while time.time() < deadline:
            try:
                signed = page.query_selector("#avatar-btn, ytd-topbar-menu-button-renderer #avatar-btn, img#img[alt]")
                url = page.url
                if signed and "accounts.google.com" not in url:
                    print("✓ signed in detected — saving profile…")
                    page.wait_for_timeout(1500)
                    ctx.close()
                    print(f"✓ profile saved: {PROFILE}")
                    return
            except Exception:
                pass
            time.sleep(2)
        ctx.close()
        print("✗ timed out waiting for sign-in — re-run and complete the Google login.")


def publish(path, title="Mr Yeti — SaathiAI test", visibility="Unlisted"):
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        print(f"✗ video not found: {path}"); return
    be = _backend()
    print(f"▶ uploading {path}  (visibility={visibility})  — watch the Chrome window…")
    try:
        r = be.execute("publish_video", profile=PROFILE, path=path, title=title,
                       description="Uploaded by SaathiAI (test).", visibility=visibility,
                       no_vision=True)
        print("\n=== RESULT ===")
        print("published:", r.get("published"), " url:", r.get("video_url"))
        print("\n=== TIMELINE ===")
        for s in r.get("timeline", []):
            mark = "✓" if s["ok"] else "✗"
            print(f"  {s['clock']}  {mark}  {s['action']:10} {s['target'][:70]}  {s['detail']}")
    except Exception as e:
        print(f"\n✗ workflow stopped: {e}")
        print("  → the last ✗ step above names the selector to fix in pages/youtube.py (or teach it)")


def check():
    """Verify we can attach to Chrome and that YouTube is logged in."""
    from playwright.sync_api import sync_playwright
    be = _backend()
    mode = f"CDP {be._cdp_url}" if be._cdp_url else f"profile {PROFILE}"
    print(f"▶ checking via {mode} …")
    with sync_playwright() as pw:
        ctx = be._context(pw, PROFILE)
        page = ctx.new_page() if getattr(ctx, "_saathi_attached", False) else \
            (ctx.pages[0] if ctx.pages else ctx.new_page())
        page.goto("https://studio.youtube.com/channel/UC/videos/upload?d=ud", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        signed = "accounts.google.com" not in page.url
        print("  final url :", page.url[:80])
        print("  logged in :", "✓ YES" if signed else "✗ NO — sign in first")
        if getattr(ctx, "_saathi_attached", False):
            page.close()
        else:
            ctx.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "login"
    if cmd == "login":
        login()
    elif cmd == "check":
        check()
    elif cmd == "publish":
        publish(*sys.argv[2:])
    else:
        print(__doc__)
