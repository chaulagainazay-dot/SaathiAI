"""HCGMS canteen queries against Supabase (REST API, service key)."""
import datetime as dt

import httpx

from .. import config

DAILY_TARGET = 30000
DAILY_BASELINE = 22000
CREDIT_LIMIT = 3000


def _sb(path: str, params: dict | None = None) -> list[dict]:
    if not config.SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL not configured in .env")
    r = httpx.get(
        f"{config.SUPABASE_URL}/rest/v1/{path}",
        params=params or {},
        headers={
            "apikey": config.SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {config.SUPABASE_SERVICE_KEY}",
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def query(topic: str) -> dict:
    today = dt.date.today().isoformat()

    if topic == "sales_today":
        rows = _sb("sales", {"select": "amount,payment_type",
                             "sale_date": f"eq.{today}"})
        total = sum(r.get("amount", 0) for r in rows)
        return {"date": today, "total_npr": total, "target_npr": DAILY_TARGET,
                "baseline_npr": DAILY_BASELINE, "entries": len(rows),
                "vs_target": total - DAILY_TARGET}

    if topic == "missing_reports":
        rows = _sb("daily_reports", {"select": "staff_name,report_type,created_at",
                                     "created_at": f"gte.{today}"})
        submitted = {r.get("staff_name") for r in rows}
        expected = {"Yabesh", "Sajana", "Hasina", "Aayush"}
        return {"submitted": sorted(submitted & expected),
                "missing": sorted(expected - submitted)}

    if topic == "credit_alerts":
        rows = _sb("credit_accounts", {"select": "customer_name,balance",
                                       "balance": "gte.2500",
                                       "order": "balance.desc"})
        return {"limit_npr": CREDIT_LIMIT,
                "accounts": [{"name": r["customer_name"], "balance": r["balance"],
                              "blocked": r["balance"] >= CREDIT_LIMIT} for r in rows]}

    if topic == "hygiene_status":
        rows = _sb("hygiene_checklists", {"select": "submitted_by,approved_by_yabesh",
                                          "created_at": f"gte.{today}"})
        return {"submitted_today": len(rows),
                "pending_approval": sum(1 for r in rows if not r.get("approved_by_yabesh"))}

    if topic == "duty_confirmation":
        tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
        rows = _sb("duty_confirmations", {"select": "person_on_duty,beans_soaking,confirmed_at",
                                          "duty_date": f"eq.{tomorrow}"})
        if rows:
            return {"confirmed": True, **rows[0]}
        return {"confirmed": False,
                "note": "AjayG has not confirmed tomorrow's 5:30am duty yet."}

    if topic == "notifications":
        rows = _sb("notifications", {"select": "type,content,created_at",
                                     "read_at": "is.null",
                                     "order": "created_at.desc", "limit": "10"})
        return {"unread": rows}

    if topic == "weekly_summary":
        week_ago = (dt.date.today() - dt.timedelta(days=7)).isoformat()
        rows = _sb("sales", {"select": "amount,sale_date",
                             "sale_date": f"gte.{week_ago}"})
        by_day: dict[str, float] = {}
        for r in rows:
            by_day[r["sale_date"]] = by_day.get(r["sale_date"], 0) + r.get("amount", 0)
        return {"daily_totals_npr": dict(sorted(by_day.items())),
                "week_total_npr": sum(by_day.values())}

    return {"error": f"unknown topic: {topic}"}
