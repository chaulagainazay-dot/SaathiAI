"""Telegram adapter — the FIRST live connector (real Bot API calls).

No OAuth dance: a bot token authenticates. The account's encrypted secret holds
{bot_token, chat_id}. Capability verbs map to Bot API methods. This is the reference
implementation every future adapter follows — a plain class whose method names match
the capability verbs; the Connector Manager passes the (decrypted) account + params.
"""
from __future__ import annotations

_API = "https://api.telegram.org/bot{token}/{method}"


def _token(acct: dict, params: dict) -> str:
    return (acct.get("secret") or {}).get("bot_token") or params.get("bot_token", "")


class TelegramAdapter:
    def send(self, acct: dict, params: dict) -> dict:
        import httpx
        token = _token(acct, params)
        chat = params.get("chat_id") or (acct.get("secret") or {}).get("chat_id")
        text = params.get("text", "")
        if not token or not chat:
            return {"ok": False, "error": "bot_token and chat_id required"}
        try:
            r = httpx.post(_API.format(token=token, method="sendMessage"),
                           json={"chat_id": chat, "text": text}, timeout=15)
            j = r.json()
        except Exception as e:
            return {"ok": False, "error": str(e)[:120]}
        return {"ok": bool(j.get("ok")), "message_id": (j.get("result") or {}).get("message_id"),
                "error": j.get("description")}

    def channels(self, acct: dict, params: dict) -> dict:
        # send to a channel is the same call with a channel chat_id (@channelname)
        return self.send(acct, params)

    def groups(self, acct: dict, params: dict) -> dict:
        return self.send(acct, params)

    def bots(self, acct: dict, params: dict) -> dict:
        """getMe — identity + health check for the bot."""
        import httpx
        token = _token(acct, params)
        if not token:
            return {"ok": False, "error": "bot_token required"}
        try:
            j = httpx.get(_API.format(token=token, method="getMe"), timeout=10).json()
        except Exception as e:
            return {"ok": False, "error": str(e)[:120]}
        return {"ok": bool(j.get("ok")), "username": (j.get("result") or {}).get("username")}


def register(register_adapter) -> None:
    register_adapter("telegram", TelegramAdapter())
