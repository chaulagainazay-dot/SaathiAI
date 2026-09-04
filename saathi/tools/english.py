"""English coaching tools — mistake tracking for spaced review."""
from ..legacy_store import legacy_memory


def log_mistake(mistake: str, correction: str) -> dict:
    legacy_memory().log_mistake(mistake, correction)
    return {"logged": True}


def progress() -> dict:
    return {"top_mistakes": legacy_memory().top_mistakes()}
