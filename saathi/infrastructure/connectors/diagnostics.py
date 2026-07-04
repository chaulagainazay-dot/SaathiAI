"""Infrastructure Diagnostics — one health snapshot the CEO dashboard consumes.

Assembles the whole infrastructure layer's status from what each service already
knows: Model Router provider availability, Browser tier availability, and every
Connector's health(). No new probing logic — diagnostics is almost free because
every component already exposes health.
"""
from __future__ import annotations


def _light(ok: bool) -> str:
    return "🟢" if ok else "🔴"


def model_router_section() -> list[dict]:
    from saathi.model_router import DEFAULT_PROVIDERS
    from saathi.llm import env_availability
    return [{"id": p.name, "available": env_availability(p.name),
             "light": _light(env_availability(p.name))}
            for p in DEFAULT_PROVIDERS]


def browser_section() -> list[dict]:
    from saathi.browser import browser
    return [{"id": name, "available": ok, "light": _light(ok)}
            for name, ok in browser.tiers_status().items()]


def connectors_section(reg=None) -> list[dict]:
    from .registry import registry as default_registry
    reg = reg or default_registry
    out = []
    for cid, h in reg.health_all().items():
        out.append({"id": cid, "status": h["status"], "light": h["light"],
                    "detail": h["detail"], "metrics": h.get("metrics", {})})
    return out


def snapshot(reg=None) -> dict:
    """Full infrastructure health, grouped like the CEO dashboard."""
    return {
        "model_router": model_router_section(),
        "browser": browser_section(),
        "connectors": connectors_section(reg),
    }
