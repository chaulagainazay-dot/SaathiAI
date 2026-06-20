"""
Standalone autopost runner for GitHub Actions.
Usage: python scripts/run_autopost.py --slot AM|PM|VIDEO

Writes secrets from env vars to files before running,
then calls the Baadar autopost functions directly.
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── 1. Hydrate secrets from env vars into files ─────────────────────────────
data_dir = ROOT / "data"
data_dir.mkdir(exist_ok=True)

# connections.json (FB/IG tokens)
conn_json = os.getenv("CONNECTIONS_JSON", "")
if conn_json:
    (data_dir / "connections.json").write_text(conn_json)
    print("✅ connections.json loaded from secret")

# firebase-admin.json (blog publishing)
fb_json = os.getenv("FIREBASE_ADMIN_JSON", "")
if fb_json:
    (ROOT / "firebase-admin.json").write_text(fb_json)
    print("✅ firebase-admin.json loaded from secret")

# growth calendar — restore from secret if exists
cal_json = os.getenv("GROWTH_CALENDAR_JSON", "")
if cal_json:
    growth_dir = data_dir / "growth"
    growth_dir.mkdir(exist_ok=True)
    from datetime import datetime
    cal_path = growth_dir / f"strategy_30day_{datetime.now().strftime('%Y-%m-%d')}.json"
    if not cal_path.exists():
        # find any existing calendar file to restore
        cal_path = sorted(growth_dir.glob("strategy_30day_*.json"))[-1] if list(growth_dir.glob("strategy_30day_*.json")) else cal_path
    cal_path.write_text(cal_json)
    print(f"✅ Growth calendar loaded from secret → {cal_path.name}")

# ── 2. Parse slot argument ───────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--slot", required=True, choices=["AM", "PM", "VIDEO"],
                    help="Which post slot to run")
args = parser.parse_args()

print(f"\n🚀 Running autopost — slot: {args.slot}")
print(f"   Time: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")

# ── 3. Run the correct autopost function ────────────────────────────────────
try:
    if args.slot in ("AM", "PM"):
        from saathi.autopost import run_social_autopost
        result = run_social_autopost(args.slot)
    else:
        from saathi.autopost import run_daily_autopost
        result = run_daily_autopost()

    print(f"\n✅ Done: {result}")

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
