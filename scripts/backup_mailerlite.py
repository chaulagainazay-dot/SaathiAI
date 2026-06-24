#!/usr/bin/env python3
"""Disaster-recovery backup for MailerLite (pielts subscriber list + campaigns).

What it backs up
----------------
1. All subscriber groups → each group's subscribers exported to JSONL.
2. Campaigns list (metadata only — no HTML body, keeps file sizes small).
3. Automations list.
4. A manifest with counts and any errors.

Output layout
-------------
data/backups/mailerlite/YYYYMMDD_HHMMSS/
    groups/<group_id>_<name>.jsonl   ← one file per group
    all_subscribers.jsonl            ← full list, de-duplicated
    campaigns.json
    automations.json
    manifest.json

Retention: keeps the last KEEP_BACKUPS snapshots (default 8).

Environment / config used
-------------------------
  MAILERLITE_API_KEY    v2 API key (from .env — already set in SaathiAI)
  MAILERLITE_GROUP_ID   primary group ID (optional, informational)
  BACKUP_MAILERLITE_DIR override output directory
  BACKUP_KEEP           how many snapshots to keep (default 8)
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# ── resolve project root ──────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from saathi import config as _cfg
    _ML_KEY_DEFAULT  = _cfg.MAILERLITE_API_KEY if hasattr(_cfg, "MAILERLITE_API_KEY") else ""
    TELEGRAM_BOT_TOKEN = _cfg.TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID   = _cfg.TELEGRAM_CHAT_ID
except Exception:
    _ML_KEY_DEFAULT    = ""
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# Resolve API key: env var takes precedence over .env via config
MAILERLITE_API_KEY = (os.getenv("MAILERLITE_API_KEY") or _ML_KEY_DEFAULT or "").strip()
BACKUP_BASE = Path(os.getenv("BACKUP_MAILERLITE_DIR",
                              str(ROOT / "data" / "backups" / "mailerlite")))
KEEP_BACKUPS = int(os.getenv("BACKUP_KEEP", "8"))

_ML_BASE = "https://connect.mailerlite.com/api"


# ── low-level API helper ──────────────────────────────────────────────────────

def _ml_get(path: str, params: dict | None = None) -> dict | list:
    """GET request to MailerLite API v2 (new connect.mailerlite.com endpoint).
    Raises on HTTP errors.  Handles 429 rate-limit with a 60-second back-off.
    """
    if not MAILERLITE_API_KEY:
        raise RuntimeError("MAILERLITE_API_KEY is not set — cannot backup subscribers.")

    qs = ""
    if params:
        from urllib.parse import urlencode
        qs = "?" + urlencode(params)

    url = f"{_ML_BASE}/{path.lstrip('/')}{qs}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {MAILERLITE_API_KEY}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    })
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = int(e.headers.get("Retry-After", "60"))
                print(f"  Rate-limited — waiting {wait}s …")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"MailerLite GET {path} failed after 3 attempts")


def _paginate(path: str, key: str = "data",
              per_page: int = 1000) -> list:
    """Fetch all pages of a paginated MailerLite endpoint."""
    results = []
    cursor = None
    while True:
        params: dict = {"limit": per_page}
        if cursor:
            params["cursor"] = cursor
        resp = _ml_get(path, params=params)
        batch = resp.get(key, []) if isinstance(resp, dict) else resp
        results.extend(batch)
        # MailerLite v2 uses cursor-based pagination in `meta.next_cursor`
        meta = resp.get("meta", {}) if isinstance(resp, dict) else {}
        cursor = meta.get("next_cursor") or None
        if not cursor or not batch:
            break
    return results


# ── helpers ───────────────────────────────────────────────────────────────────

def _telegram(msg: str):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": msg[:4000]}).encode()
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


# ── main backup routine ───────────────────────────────────────────────────────

def run_backup() -> dict:
    """Execute the full MailerLite backup. Returns a summary dict."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = BACKUP_BASE / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "groups").mkdir()

    manifest: dict = {
        "timestamp":      ts,
        "groups":         {},
        "total_subscribers": 0,
        "campaigns":      0,
        "automations":    0,
        "errors":         [],
    }

    if not MAILERLITE_API_KEY:
        msg = ("MAILERLITE_API_KEY is not set in .env — "
               "add it and retry:\n  MAILERLITE_API_KEY=your_key")
        manifest["errors"].append(msg)
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        _telegram(f"🔴 MailerLite backup FAILED\n{msg}")
        return manifest

    # ── 1. Subscriber groups ──────────────────────────────────────────────────
    try:
        groups = _paginate("groups")
    except Exception as e:
        manifest["errors"].append(f"List groups: {e}")
        groups = []

    all_ids: set = set()
    all_subs: list = []

    for group in groups:
        gid   = group.get("id", "unknown")
        gname = group.get("name", "group").replace("/", "_").replace(" ", "_")
        try:
            subs = _paginate(f"groups/{gid}/subscribers")
            fname = f"{gid}_{gname}.jsonl"
            with open(out_dir / "groups" / fname, "w", encoding="utf-8") as fh:
                for s in subs:
                    fh.write(json.dumps(s, ensure_ascii=False) + "\n")
                    sid = s.get("id") or s.get("email")
                    if sid and sid not in all_ids:
                        all_ids.add(sid)
                        all_subs.append(s)
            manifest["groups"][gname] = len(subs)
        except Exception as e:
            manifest["errors"].append(f"Group '{gname}' ({gid}): {e}")

    # ── 2. All subscribers (de-duplicated) ────────────────────────────────────
    try:
        # Fetch the global subscriber list as a catch-all
        extra = _paginate("subscribers")
        added = 0
        for s in extra:
            sid = s.get("id") or s.get("email")
            if sid and sid not in all_ids:
                all_ids.add(sid)
                all_subs.append(s)
                added += 1
        if added:
            manifest["groups"]["_ungrouped"] = added
    except Exception as e:
        manifest["errors"].append(f"All-subscribers list: {e}")

    with open(out_dir / "all_subscribers.jsonl", "w", encoding="utf-8") as fh:
        for s in all_subs:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")
    manifest["total_subscribers"] = len(all_subs)

    # ── 3. Campaigns ──────────────────────────────────────────────────────────
    try:
        campaigns = _paginate("campaigns")
        # Strip large HTML fields to keep file manageable
        slim = [{k: v for k, v in c.items()
                 if k not in ("content", "html_content", "plain_text")}
                for c in campaigns]
        (out_dir / "campaigns.json").write_text(
            json.dumps(slim, indent=2, ensure_ascii=False))
        manifest["campaigns"] = len(slim)
    except Exception as e:
        manifest["errors"].append(f"Campaigns: {e}")

    # ── 4. Automations ────────────────────────────────────────────────────────
    try:
        automations = _paginate("automations")
        (out_dir / "automations.json").write_text(
            json.dumps(automations, indent=2, ensure_ascii=False))
        manifest["automations"] = len(automations)
    except Exception as e:
        manifest["errors"].append(f"Automations: {e}")

    # ── 5. Write manifest ─────────────────────────────────────────────────────
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # ── 6. Prune old snapshots ────────────────────────────────────────────────
    snapshots = sorted(BACKUP_BASE.glob("2*"))
    for old in snapshots[:-KEEP_BACKUPS]:
        try:
            import shutil
            shutil.rmtree(old)
        except Exception:
            pass

    # ── 7. Report ─────────────────────────────────────────────────────────────
    status = "✅" if not manifest["errors"] else "⚠️"
    summary = (
        f"{status} MailerLite backup {ts}\n"
        f"Subscribers: {manifest['total_subscribers']}\n"
        f"Groups:      {len(manifest['groups'])}\n"
        f"Campaigns:   {manifest['campaigns']}\n"
        f"Automations: {manifest['automations']}\n"
        f"Saved to:    {out_dir}\n"
    )
    if manifest["errors"]:
        summary += "Errors:\n" + "\n".join(f"  • {e}" for e in manifest["errors"])

    print(summary)
    _telegram(summary)
    return manifest


if __name__ == "__main__":
    result = run_backup()
    sys.exit(1 if result.get("errors") else 0)
