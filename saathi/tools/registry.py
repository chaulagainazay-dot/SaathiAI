"""Tool registry: schemas exposed to Claude + dispatcher with privilege gating."""
from . import canteen, content, files, mac_control, n8n_tools, notes, english, system, apps
from .. import nepali, selfimprove

# Tools that require speaker verification (only Ajay's voice)
PRIVILEGED = {
    "post_social_content", "trigger_n8n_workflow", "mac_run_shortcut",
    "mac_open_app", "mac_close_app", "mac_type_text", "send_telegram",
    "search_mac_files", "read_mac_file",
    "run_shell", "write_file", "applescript", "get_mobile_link",
    "check_messages", "look_at_screen",
}

TOOL_SCHEMAS = [
    # --- Canteen / HCGMS ---
    {
        "name": "canteen_query",
        "description": "Query HCGMS canteen data from Supabase: today's sales vs target, "
                       "missing staff reports, credit accounts near/over NPR 3000 limit, "
                       "hygiene checklist status, 5:30am duty confirmation, open notifications.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string",
                          "enum": ["sales_today", "missing_reports", "credit_alerts",
                                   "hygiene_status", "duty_confirmation", "notifications",
                                   "weekly_summary"]},
            },
            "required": ["topic"],
        },
    },
    # --- Content creation ---
    {
        "name": "draft_social_content",
        "description": "Draft a Facebook post, LinkedIn post, or YouTube script/title/description "
                       "in Ajay's voice. Returns the draft for Ajay to approve. Topics are usually "
                       "the canteen, Nepali food, small-business systems, or his builder journey.",
        "input_schema": {
            "type": "object",
            "properties": {
                "platform": {"type": "string", "enum": ["facebook", "linkedin", "youtube"]},
                "topic": {"type": "string"},
                "language": {"type": "string", "enum": ["en", "ne", "mixed"], "default": "mixed"},
                "notes": {"type": "string", "description": "extra details to include"},
            },
            "required": ["platform", "topic"],
        },
    },
    {
        "name": "post_social_content",
        "description": "PRIVILEGED. Publish approved content via the n8n posting workflow. "
                       "Only call after Ajay explicitly approved the exact draft.",
        "input_schema": {
            "type": "object",
            "properties": {
                "platform": {"type": "string", "enum": ["facebook", "linkedin", "youtube"]},
                "content": {"type": "string"},
                "title": {"type": "string", "description": "for YouTube"},
            },
            "required": ["platform", "content"],
        },
    },
    # --- Automation ---
    {
        "name": "trigger_n8n_workflow",
        "description": "PRIVILEGED. Trigger an n8n workflow by name with JSON parameters "
                       "(email, calendar, file ops, custom business automations).",
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow": {"type": "string"},
                "params": {"type": "object"},
            },
            "required": ["workflow"],
        },
    },
    {
        "name": "send_telegram",
        "description": "PRIVILEGED. Send a message to Ajay's Telegram (notes-to-self, reminders, "
                       "forwarding a summary to read later).",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    # --- Mac control ---
    {
        "name": "mac_open_app",
        "description": "PRIVILEGED. Open an application on the MacBook by name.",
        "input_schema": {
            "type": "object",
            "properties": {"app_name": {"type": "string"}},
            "required": ["app_name"],
        },
    },
    {
        "name": "mac_close_app",
        "description": "PRIVILEGED. Quit/close an app on the Mac by name. Fuzzy-matches "
                       "running apps, so 'close the browser' or 'close cloud code' works.",
        "input_schema": {
            "type": "object",
            "properties": {"app_name": {"type": "string"}},
            "required": ["app_name"],
        },
    },
    {
        "name": "mac_run_shortcut",
        "description": "PRIVILEGED. Run a macOS Shortcuts automation by name.",
        "input_schema": {
            "type": "object",
            "properties": {"shortcut_name": {"type": "string"},
                           "input_text": {"type": "string"}},
            "required": ["shortcut_name"],
        },
    },
    {
        "name": "mac_type_text",
        "description": "PRIVILEGED. Type text into the frontmost app on the Mac (dictation-style).",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    # --- Notes / tasks / memory ---
    {
        "name": "manage_tasks",
        "description": "Add, list, or complete Ajay's personal work tasks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["add", "list", "complete"]},
                "title": {"type": "string"},
                "task_id": {"type": "integer"},
                "due": {"type": "string"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "remember_fact",
        "description": "Save a long-term fact about Ajay, his preferences, his business, "
                       "or things he asks you to remember.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fact": {"type": "string"},
                "category": {"type": "string", "default": "general"},
            },
            "required": ["fact"],
        },
    },
    # --- Files Ajay dragged in ---
    {
        "name": "my_files",
        "description": "List or read files Ajay has dragged into the SaathiAI app "
                       "(documents, notes, CSVs, PDFs). Use when he asks about 'my file', "
                       "'the document I uploaded', or any filename.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "read"]},
                "filename": {"type": "string"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "search_mac_files",
        "description": "PRIVILEGED. Search Ajay's Mac (Desktop, Documents, Downloads, "
                       "Google Drive) for files by name or content keywords. Use when he "
                       "asks about any file he hasn't uploaded — no dragging needed.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "read_mac_file",
        "description": "PRIVILEGED. Read a file from Ajay's Mac by full path (use "
                       "search_mac_files first to find it). Supports text, code, CSV, "
                       "JSON, PDF.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "run_shell",
        "description": "PRIVILEGED. Run a terminal command on the Mac and return its "
                       "output. Full system access. CONFIRM with Ajay first before any "
                       "command that deletes, moves, installs, or changes things; "
                       "read-only commands (ls, cat, ps, df, git status...) can run "
                       "immediately.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout_sec": {"type": "integer", "default": 60},
            },
            "required": ["command"],
        },
    },
    {
        "name": "write_file",
        "description": "PRIVILEGED. Create or edit a file in Ajay's home folder. "
                       "Confirm before overwriting existing files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "append": {"type": "boolean", "default": False},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "get_mobile_link",
        "description": "PRIVILEGED. Get the current link for using Saathi on the phone "
                       "(it changes when the Mac restarts). Use when Ajay says the "
                       "mobile app stopped working or asks for the phone link.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "applescript",
        "description": "PRIVILEGED. Control any Mac app via AppleScript: create Notes, "
                       "send iMessages (confirm first!), control Music, manage Finder "
                       "windows, read Calendar, adjust volume, etc.",
        "input_schema": {
            "type": "object",
            "properties": {"script": {"type": "string"}},
            "required": ["script"],
        },
    },
    # --- Messaging apps + screen vision ---
    {
        "name": "check_messages",
        "description": "PRIVILEGED. Open a messaging app and tell Ajay who messaged "
                       "him and what they said. Use for 'who messaged me', 'check "
                       "WhatsApp', 'kasle message gareko'. Default app is WhatsApp.",
        "input_schema": {
            "type": "object",
            "properties": {"app": {"type": "string", "default": "WhatsApp"}},
        },
    },
    {
        "name": "look_at_screen",
        "description": "PRIVILEGED. Look at whatever is on Ajay's screen and answer a "
                       "question about it ('what's on my screen', 'read this', "
                       "'what does this say'). Saathi can see and describe any app.",
        "input_schema": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
    },
    # --- Self-improvement ---
    {
        "name": "record_feedback",
        "description": "Log a signal about your own performance so you improve over "
                       "time. Call when Ajay says something was wrong/'galat', when an "
                       "action was blocked or errored, or when he praises you. "
                       "kind: wrong | blocked | error | praise | missed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string"},
                "detail": {"type": "string"},
            },
            "required": ["kind"],
        },
    },
    {
        "name": "self_improve",
        "description": "Run a self-improvement cycle now: reflect on recent feedback "
                       "into learnings and auto-tune settings. Use when Ajay says "
                       "'learn from today', 'improve yourself', or 'update yourself'.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "self_status",
        "description": "Report how Saathi is improving: feedback counts, tuned "
                       "settings, last reflection. Use when Ajay asks how you're learning.",
        "input_schema": {"type": "object", "properties": {}},
    },
    # --- Nepali learning ---
    {
        "name": "teach_nepali",
        "description": "Record a Nepali transcription correction. Call this whenever "
                       "Ajay corrects a word you misheard (e.g. he says 'I said X not Y', "
                       "or 'that word was wrong, it's X'). Saves wrong→right so you never "
                       "mishear it again.",
        "input_schema": {
            "type": "object",
            "properties": {
                "wrong": {"type": "string", "description": "what you mistakenly heard"},
                "right": {"type": "string", "description": "the correct Nepali word/phrase"},
            },
            "required": ["wrong", "right"],
        },
    },
    {
        "name": "nepali_progress",
        "description": "Show how much Nepali Saathi has learned: corrections stored and "
                       "phrases overheard. Use when Ajay asks how your Nepali is improving.",
        "input_schema": {"type": "object", "properties": {}},
    },
    # --- English coaching ---
    {
        "name": "english_log_mistake",
        "description": "In English-coach mode: log a grammar/vocab mistake Ajay made and its "
                       "correction, so recurring patterns can be reviewed later.",
        "input_schema": {
            "type": "object",
            "properties": {
                "mistake": {"type": "string"},
                "correction": {"type": "string"},
            },
            "required": ["mistake", "correction"],
        },
    },
    {
        "name": "english_progress",
        "description": "Show Ajay's most frequent English mistakes for review/practice.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

_HANDLERS = {
    "canteen_query": canteen.query,
    "draft_social_content": content.draft,
    "post_social_content": content.post,
    "trigger_n8n_workflow": n8n_tools.trigger,
    "send_telegram": n8n_tools.send_telegram,
    "mac_open_app": mac_control.open_app,
    "mac_close_app": mac_control.close_app,
    "mac_run_shortcut": mac_control.run_shortcut,
    "mac_type_text": mac_control.type_text,
    "my_files": files.my_files,
    "search_mac_files": files.search_mac_files,
    "read_mac_file": files.read_mac_file,
    "manage_tasks": notes.manage_tasks,
    "remember_fact": notes.remember_fact,
    "run_shell": system.run_shell,
    "write_file": system.write_file,
    "applescript": system.applescript,
    "get_mobile_link": system.get_mobile_link,
    "check_messages": apps.check_messages,
    "look_at_screen": apps.look_at_screen,
    "record_feedback": lambda kind, detail="": selfimprove.record_feedback(kind, detail),
    "self_improve": lambda: selfimprove.run_cycle(),
    "self_status": lambda: selfimprove.status(),
    "teach_nepali": lambda wrong, right: nepali.teach(wrong, right),
    "nepali_progress": lambda: nepali.progress(),
    "english_log_mistake": english.log_mistake,
    "english_progress": english.progress,
}


def execute_tool(name: str, args: dict, speaker_verified: bool = False) -> dict:
    if name in PRIVILEGED and not speaker_verified:
        return {"error": "speaker_not_verified",
                "message": "This action is only allowed for Ajay's verified voice. "
                           "Ask him to re-verify (say the wake phrase clearly) or use the app."}
    handler = _HANDLERS.get(name)
    if not handler:
        return {"error": f"unknown tool: {name}"}
    try:
        return handler(**args)
    except Exception as e:  # surface errors to the model so it can explain
        return {"error": type(e).__name__, "message": str(e)}
