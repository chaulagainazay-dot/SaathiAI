from __future__ import annotations
"""HCGMS canteen queries against the live Supabase (REST API, service key).

Schema matched to the real HCGMS database (June 2026).
"""
import datetime as dt

import httpx

from .. import config

DAILY_TARGET = 30000
DAILY_BASELINE = 22000
CREDIT_LIMIT = 3000

# staff roles expected to file a daily report, and their display names
REPORT_ROLES = {"yabesh": "Yabesh", "sajana": "Sajana", "hasina": "Hasina"}


def _sb(path: str, params: dict | None = None) -> list[dict]:
    if not config.SUPABASE_URL or "YOUR" in config.SUPABASE_URL:
        raise RuntimeError("Supabase not configured in .env")
    r = httpx.get(
        f"{config.SUPABASE_URL}/rest/v1/{path}",
        params=params or {},
        headers={"apikey": config.SUPABASE_SERVICE_KEY,
                 "Authorization": f"Bearer {config.SUPABASE_SERVICE_KEY}"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def query(topic: str) -> dict:
    today = dt.date.today().isoformat()

    if topic == "sales_today":
        rows = _sb("sales", {"select": "net_amount,payment_method",
                             "sale_date": f"eq.{today}",
                             "invoice_status": "neq.cancelled"})
        total = sum(r.get("net_amount") or 0 for r in rows)
        credit = sum(r.get("net_amount") or 0 for r in rows
                     if (r.get("payment_method") or "").lower() == "credit")
        return {"date": today, "total_npr": round(total),
                "target_npr": DAILY_TARGET, "baseline_npr": DAILY_BASELINE,
                "vs_target": round(total - DAILY_TARGET), "entries": len(rows),
                "credit_npr": round(credit)}

    if topic == "missing_reports":
        rows = _sb("daily_reports", {"select": "reporter_role",
                                     "report_date": f"eq.{today}"})
        submitted_roles = {(r.get("reporter_role") or "").lower() for r in rows}
        submitted = sorted(REPORT_ROLES[r] for r in REPORT_ROLES if r in submitted_roles)
        missing = sorted(REPORT_ROLES[r] for r in REPORT_ROLES
                         if r not in submitted_roles)
        return {"date": today, "submitted": submitted, "missing": missing}

    if topic == "credit_alerts":
        rows = _sb("credit_accounts", {"select": "name,balance",
                                       "balance": "gte.2500",
                                       "is_inactive": "eq.false",
                                       "order": "balance.desc"})
        over = [r for r in rows if (r.get("balance") or 0) >= CREDIT_LIMIT]
        total_over = round(sum(r.get("balance") or 0 for r in over))
        return {"limit_npr": CREDIT_LIMIT,
                "accounts_over_limit": len(over),
                "total_outstanding_over_limit_npr": total_over,
                "top_accounts": [{"name": r["name"],
                                  "balance": round(r.get("balance") or 0)}
                                 for r in rows[:10]]}

    if topic == "hygiene_status":
        rows = _sb("hygiene_checklists", {"select": "staff_name,approved_by_yabesh",
                                          "check_date": f"eq.{today}"})
        return {"submitted_today": len(rows),
                "pending_approval": sum(1 for r in rows
                                        if not r.get("approved_by_yabesh")),
                "submitted_by": [r.get("staff_name") for r in rows]}

    if topic == "duty_confirmation":
        tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
        rows = _sb("duty_confirmations", {"select": "duty_person,confirmed_by,notes",
                                          "confirm_date": f"eq.{tomorrow}"})
        if rows:
            return {"confirmed": True, "duty_person": rows[0].get("duty_person"),
                    "confirmed_by": rows[0].get("confirmed_by"),
                    "notes": rows[0].get("notes")}
        return {"confirmed": False,
                "note": "AjayG hasn't confirmed tomorrow's 5:30am duty yet."}

    if topic == "notifications":
        rows = _sb("notifications", {"select": "type,title,body,is_read,created_at",
                                     "order": "created_at.desc", "limit": "10"})
        return {"recent": rows, "unread": sum(1 for r in rows if not r.get("is_read"))}

    if topic == "weekly_summary":
        week_ago = (dt.date.today() - dt.timedelta(days=7)).isoformat()
        rows = _sb("sales", {"select": "net_amount,sale_date",
                             "sale_date": f"gte.{week_ago}",
                             "invoice_status": "neq.cancelled"})
        by_day: dict[str, float] = {}
        for r in rows:
            by_day[r["sale_date"]] = by_day.get(r["sale_date"], 0) + (r.get("net_amount") or 0)
        return {"daily_totals_npr": {d: round(v) for d, v in sorted(by_day.items())},
                "week_total_npr": round(sum(by_day.values()))}

    return {"error": f"unknown topic: {topic}"}
