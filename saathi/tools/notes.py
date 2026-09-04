"""Tasks + long-term memory tools (backed by the shared Memory db)."""
from ..legacy_store import legacy_memory


def manage_tasks(action: str, title: str = "", task_id: int = 0, due: str = "") -> dict:
    mem = legacy_memory()
    if action == "add":
        tid = mem.add_task(title, due or None)
        return {"added": {"id": tid, "title": title, "due": due or None}}
    if action == "complete":
        mem.complete_task(task_id)
        return {"completed": task_id}
    return {"open_tasks": mem.open_tasks()}


def remember_fact(fact: str, category: str = "general") -> dict:
    legacy_memory().save_fact(fact, category)
    return {"remembered": fact}
