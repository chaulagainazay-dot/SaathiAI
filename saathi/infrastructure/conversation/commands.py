"""Command routing — the fast layer checked before the LLM.

Generalizes what the Telegram companion already does: `/brief`, `/revenue`,
`/approve`, `/run`, … resolve deterministically; anything else falls through to
Executive Intelligence. Returns the command reply text, or None to fall through.
"""
from __future__ import annotations

from typing import Callable

# a command handler: (message, session) -> reply text | None
CommandHandler = Callable[[str, "object"], "str | None"]


def default_commands(message: str, session) -> str | None:
    """Bridge to the existing CEO command layer (telegram_ceo.handle_command)."""
    try:
        from saathi.telegram_ceo import handle_command
        return handle_command(message)
    except Exception:
        return None


def is_command(message: str) -> bool:
    return message.strip().startswith("/")
