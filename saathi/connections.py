"""Social account connections — one place where Ajay links all his platforms so
Baadar can post + plan across every one of them.

Stored as plain JSON (data/connections.json). No paid aggregator. Each platform
has a posting METHOD describing how Baadar actually publishes there:
  browser = post through the already-logged-in browser (Facebook/LinkedIn — no API keys)
  n8n     = POST to an n8n webhook that holds that platform's login (YouTube/Instagram/X)
  manual  = Baadar prepares the caption + video and Ajay does the final upload (TikTok)
"""
import json

from . import config

PATH = config.ROOT / "data" / "connections.json"

# How automated each platform can realistically be, for free, today.
_N8N = config.N8N_WEBHOOK_BASE  # e.g. http://127.0.0.1:5678/webhook

DEFAULTS = {
    "facebook":  {"connected": False, "method": "n8n",    "handle": "pieltsapp",  "webhook": f"{_N8N}/post-social"},
    "instagram": {"connected": False, "method": "n8n",    "handle": "@pieltsapp", "webhook": f"{_N8N}/post-social"},
    "tiktok":    {"connected": False, "method": "manual", "handle": "@pieltsapp", "webhook": ""},
    "youtube":   {"connected": False, "method": "n8n",    "handle": "@pieltsapp", "webhook": f"{_N8N}/youtube-upload"},
    "linkedin":  {"connected": False, "method": "browser","handle": "",           "webhook": ""},
    "x":         {"connected": False, "method": "n8n",    "handle": "",           "webhook": f"{_N8N}/post-social"},
}
_FIELDS = ("connected", "method", "handle", "webhook")


def get_all() -> dict:
    data = {k: dict(v) for k, v in DEFAULTS.items()}
    try:
        for k, v in json.loads(PATH.read_text()).items():
            data.setdefault(k, {"connected": False, "method": "manual",
                                "handle": "", "webhook": ""}).update(v)
    except Exception:
        pass
    return data


def save_one(platform: str, cfg: dict) -> dict:
    data = get_all()
    p = (platform or "").lower()
    base = data.get(p, {"connected": False, "method": "manual", "handle": "", "webhook": ""})
    base.update({k: cfg[k] for k in _FIELDS if k in cfg})
    data[p] = base
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(data, indent=2))
    return data[p]


def connected() -> list:
    return [k for k, v in get_all().items() if v.get("connected")]
