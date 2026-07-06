"""Hospital Cafeteria business event source → Evidence."""
from __future__ import annotations
from saathi.evidence.schema import Evidence
_C = "cafeteria"


def handle(event_type: str, payload: dict, *, subject: str = "") -> list[Evidence]:
    p = payload or {}
    subject = subject or p.get("date") or p.get("item") or ""
    if event_type == "meal.sold":
        return [Evidence(department=_C, project="hcg_canteen", episode=subject, director="menu_planner",
                         status="sold", metrics={"item": p.get("item", ""), "qty": p.get("qty"),
                                                 "revenue": p.get("revenue"), "profit": p.get("profit")})]
    if event_type in ("waste.recorded", "inventory.used"):
        return [Evidence(department=_C, project="hcg_canteen", episode=subject, director="menu_planner",
                         status=event_type.split(".")[0],
                         metrics={"item": p.get("item", ""), "waste": p.get("waste"),
                                  "used": p.get("used"), "day": p.get("day", "")})]
    if event_type == "customer.feedback":
        return [Evidence(department=_C, project="hcg_canteen", episode=subject, director="menu_planner",
                         status="feedback", feedback={"rating": p.get("rating"), "text": p.get("text", "")})]
    return []
