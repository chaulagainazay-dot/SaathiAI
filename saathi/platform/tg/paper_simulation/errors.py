"""Paper simulation errors — fail-closed."""
from __future__ import annotations


class PaperSimError(Exception):
    def __init__(self, code: str, message: str, *, detail: dict | None = None):
        self.code = code
        self.message = message
        self.detail = detail or {}
        super().__init__(f"{code}: {message}")

    def to_dict(self) -> dict:
        return {
            "ok": False,
            "code": self.code,
            "message": self.message,
            "detail": self.detail,
            "fail_closed": True,
            "simulation_only": True,
        }
