"""Engine adapter registration (not model routing).

Duplicate registration is rejected unless replace=True.
ModelRouter remains the sole authority for model *selection*.
"""
from __future__ import annotations

from typing import Callable, Optional, Type, Union

from saathi.inference.engine import InferenceEngine
from saathi.inference.errors import EngineError

EngineFactory = Callable[[], InferenceEngine]
EngineEntry = Union[InferenceEngine, Type[InferenceEngine], EngineFactory]


class EngineRegistry:
    def __init__(self) -> None:
        self._engines: dict[str, InferenceEngine] = {}
        self._factories: dict[str, EngineFactory] = {}

    def register(
        self,
        engine_id: str,
        engine: EngineEntry,
        *,
        replace: bool = False,
    ) -> None:
        if not engine_id or not str(engine_id).strip():
            raise EngineError("engine_id is required")
        if engine_id in self._engines or engine_id in self._factories:
            if not replace:
                raise EngineError(f"engine already registered: {engine_id}")
            self.unregister(engine_id)

        if isinstance(engine, InferenceEngine):
            if getattr(engine, "engine_id", None) and engine.engine_id != engine_id:
                # allow aliasing but keep instance id if set
                pass
            self._engines[engine_id] = engine
            return

        if isinstance(engine, type) and issubclass(engine, InferenceEngine):
            self._factories[engine_id] = engine  # type: ignore[assignment]
            return

        if callable(engine):
            self._factories[engine_id] = engine  # type: ignore[assignment]
            return

        raise EngineError(f"invalid engine registration for {engine_id}")

    def unregister(self, engine_id: str) -> None:
        self._engines.pop(engine_id, None)
        self._factories.pop(engine_id, None)

    def get(self, engine_id: str) -> Optional[InferenceEngine]:
        if engine_id in self._engines:
            return self._engines[engine_id]
        factory = self._factories.get(engine_id)
        if factory is None:
            return None
        inst = factory()
        self._engines[engine_id] = inst
        return inst

    def ids(self) -> list[str]:
        return sorted(set(self._engines) | set(self._factories))

    def clear(self) -> None:
        self._engines.clear()
        self._factories.clear()

    def __contains__(self, engine_id: str) -> bool:
        return engine_id in self._engines or engine_id in self._factories


_GLOBAL = EngineRegistry()


def get_engine_registry() -> EngineRegistry:
    return _GLOBAL


def reset_engine_registry() -> None:
    _GLOBAL.clear()
