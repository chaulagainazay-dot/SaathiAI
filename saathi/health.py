"""Self-health watchdog — checks every Baadar subsystem so silent failures get caught."""
import os
import shutil

import httpx

from . import config


def _c(name, status, detail=""):
    return {"name": name, "status": status, "detail": detail}


def health_check() -> dict:
    checks = []
    try:
        r = httpx.get(f"http://127.0.0.1:{config.PORT}/api/v1/health", timeout=4)
        checks.append(_c("API server", "ok" if r.status_code == 200 else "fail"))
    except Exception as e:
        checks.append(_c("API server", "fail", str(e)[:50]))
    try:
        r = httpx.get("http://127.0.0.1:5678/", timeout=4)
        checks.append(_c("n8n (auto-post)", "ok" if r.status_code < 500 else "fail"))
    except Exception:
        checks.append(_c("n8n (auto-post)", "fail", "not running"))
    tg = bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)
    checks.append(_c("Telegram alerts", "ok" if tg else "fail", "" if tg else "chat id not set"))
    try:
        from . import autopost
        left = len(autopost.pending())
        checks.append(_c("Video queue", "ok" if left > 0 else "warn", f"{left} queued"))
    except Exception:
        checks.append(_c("Video queue", "fail"))
    try:
        from . import connections
        yt = connections.get_all().get("youtube", {})
        checks.append(_c("YouTube auto-post", "ok" if (yt.get("connected") and yt.get("webhook")) else "warn"))
    except Exception:
        checks.append(_c("YouTube auto-post", "fail"))
    checks.append(_c("YouTube stats key", "ok" if os.getenv("YT_API_KEY") else "warn", "" if os.getenv("YT_API_KEY") else "dashboard stats off"))
    checks.append(_c("Blog auto-publish key", "ok" if os.path.exists(os.path.expanduser("~/SaathiAI/firebase-admin.json")) else "warn"))
    try:
        free = shutil.disk_usage(str(config.ROOT)).free / 1e9
        checks.append(_c("Disk space", "ok" if free > 2 else "warn", f"{free:.1f} GB free"))
    except Exception:
        pass
    fails = [c for c in checks if c["status"] == "fail"]
    warns = [c for c in checks if c["status"] == "warn"]
    return {"overall": "fail" if fails else ("warn" if warns else "ok"),
            "checks": checks, "fails": fails, "warns": warns}
