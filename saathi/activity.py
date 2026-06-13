"""Live activity feed — mirrors every step Baadar takes while it works on a task,
so Ajay can watch what it's doing in real time inside the app.

The agent pushes events here (a thought, a tool it's running, the result); the web
client polls /api/v1/agent/activity and shows them as a live step list. Purely
in-memory and best-effort — never blocks or breaks a reply if anything goes wrong.
"""
import threading
import time
from collections import defaultdict, deque

_LOCK = threading.Lock()
_EVENTS: dict = defaultdict(lambda: deque(maxlen=80))
_SEQ: dict = defaultdict(int)

# Friendly, human-readable phrase for each tool so the steps read like a person
# narrating, not raw function names. Unknown tools fall back to a tidied name.
_LABELS = {
    "make_flow_prompts":     "🎬 Writing today's Mr Yeti video scenes",
    "make_talking_yeti":     "🗣️ Making the talking Yeti video",
    "make_video":            "🎞️ Building a captioned video",
    "generate_content_pack": "📝 Writing the posts & captions",
    "send_telegram":         "📲 Sending you a Telegram",
    "send_video":            "📲 Sending the video to Telegram",
    "post_facebook":         "📘 Posting to Facebook",
    "post_linkedin":         "💼 Posting to LinkedIn",
    "look_at_screen":        "👀 Looking at your screen",
    "check_messages":        "💬 Checking your messages",
    "mac_open_app":          "🖥️ Opening an app",
    "mac_close_app":         "🖥️ Closing an app",
    "mac_type_text":         "⌨️ Typing for you",
    "mac_run_shortcut":      "⚡ Running a shortcut",
    "run_shell":             "🖥️ Running a Mac command",
    "applescript":           "🍎 Running an AppleScript",
    "web_search":            "🔎 Searching the web",
    "research":              "🔎 Researching",
    "read_file":             "📄 Reading a file",
    "write_file":            "💾 Saving a file",
    "list_files":            "📁 Looking through files",
    "calendar":              "📅 Checking the calendar",
    "send_email":            "✉️ Drafting an email",
    "remember":              "🧠 Saving to memory",
}


def label_for(tool: str, args: dict | None = None) -> str:
    base = _LABELS.get(tool) or "⚙️ " + tool.replace("_", " ").capitalize()
    # add a short hint from a recognisable argument (topic/query/text)
    if args:
        for k in ("topic", "query", "text", "subject", "path"):
            v = args.get(k)
            if isinstance(v, str) and v.strip():
                base += f": {v.strip()[:50]}"
                break
    return base


def _summarize(result) -> str:
    """One short line describing what a tool returned."""
    try:
        if isinstance(result, dict):
            for k in ("status", "topic", "stored", "path", "message", "error"):
                if k in result and result[k]:
                    return f"✓ {k}: {str(result[k])[:60]}"
            return "✓ done"
        s = str(result).strip().replace("\n", " ")
        return ("✓ " + s[:70]) if s else "✓ done"
    except Exception:
        return "✓ done"


def log(session_id: str, kind: str, text: str):
    """kind: 'start' | 'think' | 'tool' | 'result' | 'done'"""
    try:
        with _LOCK:
            _SEQ[session_id] += 1
            _EVENTS[session_id].append({
                "seq": _SEQ[session_id], "kind": kind,
                "text": text, "ts": round(time.time(), 3),
            })
    except Exception:
        pass


def log_tool(session_id: str, tool: str, args: dict | None = None):
    log(session_id, "tool", label_for(tool, args))


def log_result(session_id: str, result):
    log(session_id, "result", _summarize(result))


def since(session_id: str, after: int = 0) -> list:
    with _LOCK:
        return [e for e in _EVENTS[session_id] if e["seq"] > after]


def clear(session_id: str):
    with _LOCK:
        _EVENTS[session_id].clear()
