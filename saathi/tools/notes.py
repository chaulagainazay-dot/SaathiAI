"""Tasks + long-term memory tools (backed by the shared Memory db)."""
from .. import config
from ..memory import Memory

_mem = Memory(config.DB_PATH)


def manage_tasks(action: str, title: str = "", task_id: int = 0, due: str = "") -> dict:
    if action == "add":
        tid = _mem.add_task(title, due or None)
        return {"added": {"id": tid, "title": title, "due": due or None}}
    if action == "complete":
        _mem.complete_task(task_id)
        return {"completed": task_id}
    return {"open_tasks": _mem.open_tasks()}


def remember_fact(fact: str, category: str = "general") -> dict:
    _mem.save_fact(fact, category)
    return {"remembered": fact}
