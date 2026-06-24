#!/usr/bin/env python3
"""Disaster-recovery backup for Firebase / Firestore (pielts project).

What it backs up
----------------
1. Firestore — every collection exported to newline-delimited JSON.
2. Firebase Auth users — exported to auth_users.json.
3. Firebase Hosting meta — records the live deploy URL for reference.

Output layout
-------------
data/backups/firebase/YYYYMMDD_HHMMSS/
    firestore/<collection>.jsonl
    auth_users.json
    hosting_meta.json
    manifest.json        ← summary with doc counts, timestamps, errors

Retention: keeps the last KEEP_BACKUPS snapshots (default 8).

Environment / config used
-------------------------
  FIREBASE_ADMIN_JSON   path to service-account JSON (default: <root>/firebase-admin.json)
  BACKUP_FIREBASE_DIR   override output directory
  BACKUP_KEEP           how many snapshots to keep (default 8)
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# ── resolve project root so we can import saathi.config ──────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from saathi import config as _cfg
    TELEGRAM_BOT_TOKEN = _cfg.TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID   = _cfg.TELEGRAM_CHAT_ID
except Exception:
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

FIREBASE_ADMIN_JSON = Path(os.getenv("FIREBASE_ADMIN_JSON", str(ROOT / "firebase-admin.json")))
BACKUP_BASE = Path(os.getenv("BACKUP_FIREBASE_DIR", str(ROOT / "data" / "backups" / "firebase")))
KEEP_BACKUPS = int(os.getenv("BACKUP_KEEP", "8"))


# ── helpers ───────────────────────────────────────────────────────────────────

def _telegram(msg: str):
    """Best-effort Telegram notification."""
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return
    try:
        import urllib.request
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": msg[:4000]}).encode()
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def _serialize(value):
    """Convert Firestore-native types to JSON-serialisable Python types."""
    from google.cloud.firestore_v1 import DocumentReference
    from google.protobuf.timestamp_pb2 import Timestamp  # type: ignore

    if hasattr(value, "isoformat"):          # datetime / date
        return value.isoformat()
    if isinstance(value, DocumentReference):
        return {"__ref__": value.path}
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize(i) for i in value]
    return value


# ── main backup routine ───────────────────────────────────────────────────────

def run_backup() -> dict:
    """Execute the full Firebase backup.  Returns a summary dict."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = BACKUP_BASE / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "firestore").mkdir()

    manifest: dict = {
        "timestamp": ts,
        "collections": {},
        "auth_users": 0,
        "errors": [],
    }

    # ── 0. Initialise Firebase Admin SDK ─────────────────────────────────────
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore, auth
    except ImportError:
        msg = ("firebase-admin not installed — run:\n"
               "  pip install firebase-admin\n"
               "then retry.")
        manifest["errors"].append(msg)
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        _telegram(f"🔴 Firebase backup FAILED\n{msg}")
        return manifest

    if not FIREBASE_ADMIN_JSON.exists():
        msg = f"Service-account file not found: {FIREBASE_ADMIN_JSON}"
        manifest["errors"].append(msg)
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        _telegram(f"🔴 Firebase backup FAILED\n{msg}")
        return manifest

    # Re-use existing app if already initialised (e.g. running inside Baadar)
    try:
        app = firebase_admin.get_app("backup")
    except ValueError:
        cred = credentials.Certificate(str(FIREBASE_ADMIN_JSON))
        app = firebase_admin.initialize_app(cred, name="backup")

    # ── 1. Firestore export ───────────────────────────────────────────────────
    db = firestore.client(app=app)
    try:
        collections = list(db.collections())
    except Exception as e:
        manifest["errors"].append(f"Firestore list collections: {e}")
        collections = []

    for col_ref in collections:
        col_name = col_ref.id
        jsonl_path = out_dir / "firestore" / f"{col_name}.jsonl"
        count = 0
        try:
            with open(jsonl_path, "w", encoding="utf-8") as fh:
                for doc in col_ref.stream():
                    row = {"__id__": doc.id}
                    row.update(_serialize(doc.to_dict() or {}))
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    count += 1
            manifest["collections"][col_name] = count
        except Exception as e:
            manifest["errors"].append(f"Firestore collection '{col_name}': {e}")

    # ── 2. Auth users export ──────────────────────────────────────────────────
    users = []
    try:
        page = auth.list_users(app=app)
        while page:
            for u in page.users:
                users.append({
                    "uid":           u.uid,
                    "email":         u.email,
                    "display_name":  u.display_name,
                    "phone_number":  u.phone_number,
                    "disabled":      u.disabled,
                    "email_verified": u.email_verified,
                    "creation_time": u.user_metadata.creation_timestamp,
                    "last_sign_in":  u.user_metadata.last_sign_in_timestamp,
                    "provider_ids":  [p.provider_id for p in u.provider_data],
                })
            page = page.get_next_page()
        (out_dir / "auth_users.json").write_text(
            json.dumps(users, indent=2, ensure_ascii=False))
        manifest["auth_users"] = len(users)
    except Exception as e:
        manifest["errors"].append(f"Auth export: {e}")

    # ── 3. Hosting meta (project ID from service-account) ────────────────────
    try:
        sa = json.loads(FIREBASE_ADMIN_JSON.read_text())
        hosting_meta = {
            "project_id":    sa.get("project_id"),
            "client_email":  sa.get("client_email"),
            "hosting_url":   f"https://{sa.get('project_id')}.web.app",
            "backup_ts":     ts,
        }
        (out_dir / "hosting_meta.json").write_text(
            json.dumps(hosting_meta, indent=2))
    except Exception as e:
        manifest["errors"].append(f"Hosting meta: {e}")

    # ── 4. Write manifest ─────────────────────────────────────────────────────
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # ── 5. Prune old snapshots ────────────────────────────────────────────────
    snapshots = sorted(BACKUP_BASE.glob("2*"))   # all YYYYMMDD_* dirs
    for old in snapshots[:-KEEP_BACKUPS]:
        try:
            import shutil
            shutil.rmtree(old)
        except Exception:
            pass

    # ── 6. Report ─────────────────────────────────────────────────────────────
    total_docs = sum(manifest["collections"].values())
    status = "✅" if not manifest["errors"] else "⚠️"
    summary = (
        f"{status} Firebase backup {ts}\n"
        f"Collections: {len(manifest['collections'])} ({total_docs} docs)\n"
        f"Auth users:  {manifest['auth_users']}\n"
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
