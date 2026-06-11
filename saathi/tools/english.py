"""English coaching tools — mistake tracking for spaced review."""
from .. import config
from ..memory import Memory

_mem = Memory(config.DB_PATH)


def log_mistake(mistake: str, correction: str) -> dict:
    _mem.log_mistake(mistake, correction)
    return {"logged": True}


def progress() -> dict:
    return {"top_mistakes": _mem.top_mistakes()}
