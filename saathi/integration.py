"""Platform Integration — products feed the shared Learning Runtime (M3 Sprint).

Dev Rule #2 made real: every product records its experience as platform Episodes
so the Promotion Engine, Learning Engine, and Knowledge Graph can improve it.
No product implements its own memory/learning — they call the platform.

    product interaction → ingest_episode → PlatformMemory → Promotion → Learning
                                                          → (better future decisions)

PIELTS is the first integration: a student interaction becomes an Episode, so
the tutor continuously improves from what it sees. The same helper serves HCG
POS, AI Studio, Live Signal — one memory, one learning loop.

Testable in isolation (AP-12): the platform memory + publisher are injectable.
"""
from __future__ import annotations

from typing import Callable

from saathi.memory.platform import PlatformMemory, MemoryScope, RetentionPolicy

_platform_memory: PlatformMemory | None = None
_publisher: "Callable[[str, dict], None] | None" = None


def get_platform_memory() -> PlatformMemory:
    """Process-wide platform memory (products share ONE store)."""
    global _platform_memory
    if _platform_memory is None:
        from saathi import config
        _platform_memory = PlatformMemory(str(config.ROOT / "data" / "platform_memory.db"))
    return _platform_memory


def set_platform_memory(mem: PlatformMemory) -> None:
    """For tests / explicit wiring."""
    global _platform_memory
    _platform_memory = mem


def set_publisher(publish: "Callable[[str, dict], None]") -> None:
    global _publisher
    _publisher = publish


def _emit(name: str, payload: dict) -> None:
    if _publisher is not None:
        try:
            _publisher(name, payload)
        except Exception:
            pass


# ── generic product ingestion ─────────────────────────────────────────────
def ingest_episode(*, agent: str, department: str, product: str, intent: str,
                   action: str, result: str, outcome: str = "success",
                   quality_score: float = 0.0, user: str | None = None,
                   metadata: dict | None = None,
                   scope: MemoryScope = MemoryScope.PRODUCT,
                   retention: RetentionPolicy = RetentionPolicy.STANDARD) -> int:
    """Any product records an execution as a platform Episode."""
    mem = get_platform_memory()
    eid = mem.record_episode(
        agent=agent, department=department, product=product, user=user,
        intent=intent, action=action, result=result, outcome=outcome,
        quality_score=quality_score, scope=scope, retention=retention,
        metadata=metadata or {})
    _emit("execution.recorded",
          {"episode_id": eid, "product": product, "intent": intent, "outcome": outcome})
    return eid


# ── PIELTS-specific convenience ────────────────────────────────────────────
def ingest_pielts_interaction(*, student_id: str, skill: str, input_text: str,
                              response: str, band_est: float | None = None,
                              outcome: str = "success", **extra) -> int:
    """A PIELTS tutoring turn → a platform Episode. This is what makes pielts a
    continuously-improving tutor: its interactions now feed the Learning Runtime."""
    mem = get_platform_memory()
    eid = mem.record_pielts_interaction(
        student_id=student_id, skill=skill, input_text=input_text,
        response=response, band_est=band_est, outcome=outcome, **extra)
    _emit("execution.recorded",
          {"episode_id": eid, "product": "pielts",
           "intent": f"ielts_{skill}_practice", "outcome": outcome})
    return eid
