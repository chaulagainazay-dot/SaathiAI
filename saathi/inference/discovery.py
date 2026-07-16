"""Runtime engine discovery and health aggregation.

Does not select models — only reports which engines are reachable.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from saathi.inference.engine import InferenceEngine
from saathi.inference.registry import EngineRegistry


@dataclass
class EngineHealthReport:
    engine_id: str
    ok: bool
    models: list[str] = field(default_factory=list)
    error: str = ""
    checked_at: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "ok": self.ok,
            "models": list(self.models),
            "error": self.error,
            "checked_at": self.checked_at,
            "raw": self.raw,
        }


async def probe_engine(engine_id: str, engine: InferenceEngine) -> EngineHealthReport:
    now = time.time()
    try:
        health = await engine.health()
        ok = bool(health.get("ok")) if isinstance(health, dict) else bool(health)
        models: list[str] = []
        if ok:
            try:
                models = list(await engine.list_models())
            except Exception as e:
                return EngineHealthReport(
                    engine_id=engine_id,
                    ok=False,
                    error=f"list_models failed: {e}",
                    checked_at=now,
                    raw=health if isinstance(health, dict) else {},
                )
        return EngineHealthReport(
            engine_id=engine_id,
            ok=ok,
            models=models,
            checked_at=now,
            raw=health if isinstance(health, dict) else {},
            error="" if ok else str((health or {}).get("error", "unhealthy")),
        )
    except Exception as e:
        return EngineHealthReport(
            engine_id=engine_id,
            ok=False,
            error=str(e),
            checked_at=now,
        )


async def discover_engines(
    registry: EngineRegistry,
    *,
    only: Optional[list[str]] = None,
) -> list[EngineHealthReport]:
    ids = only if only is not None else registry.ids()
    reports: list[EngineHealthReport] = []
    for eid in ids:
        engine = registry.get(eid)
        if engine is None:
            reports.append(
                EngineHealthReport(engine_id=eid, ok=False, error="not registered", checked_at=time.time())
            )
            continue
        reports.append(await probe_engine(eid, engine))
    return reports


def healthy_engine_ids(reports: list[EngineHealthReport]) -> list[str]:
    return [r.engine_id for r in reports if r.ok]


def exclude_unhealthy(
    ordered_engine_ids: list[str],
    reports: list[EngineHealthReport],
) -> list[str]:
    """Preserve order; drop engines that failed health."""
    ok = {r.engine_id for r in reports if r.ok}
    known = {r.engine_id for r in reports}
    out = []
    for eid in ordered_engine_ids:
        if eid in known and eid not in ok:
            continue
        out.append(eid)
    return out


def discover_engines_sync(registry: EngineRegistry, **kwargs) -> list[EngineHealthReport]:
    return asyncio.run(discover_engines(registry, **kwargs))
