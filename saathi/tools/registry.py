"""Tool registry: schemas exposed to Claude + dispatcher with privilege gating."""
from . import (canteen, content, files, mac_control, n8n_tools, notes, english,
               system, apps, research, calendar as cal, email_tool, content_studio,
               projects)
from .. import nepali, selfimprove

# Tools that require speaker verification (only Ajay's voice)
PRIVILEGED = {
    "send_email",
    "post_social_content", "post_to_all_socials", "deploy_ielts_site", "publish_to_youtube", "queue_video",
    "trigger_n8n_workflow", "mac_run_shortcut",
    "mac_open_app", "mac_close_app", "mac_type_text", "send_telegram",
    "search_mac_files", "read_mac_file",
    "run_shell", "write_file", "applescript", "get_mobile_link",
    "check_messages", "look_at_screen",
    "register_project", "project_run", "project_edit_file",
    "send_video_to_phone",
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
    {
        "name": "make_daily_kit",
        "description": "Generate ONE full day of content at once: a Mr Yeti video script, a "
                       "Facebook post, an Instagram caption + hashtags, and a publish-ready blog "
                       "post. Use when Ajay says 'make today\'s content/kit'.",
        "input_schema": {"type": "object", "properties": {"topic": {"type": "string"}}},
    },
    {
        "name": "make_blog_post",
        "description": "Auto-write a daily IELTS blog post (title, excerpt, markdown content) for "
                       "pielts.web.app in Mr Yeti's voice.",
        "input_schema": {"type": "object", "properties": {"topic": {"type": "string"}}},
    },
    {
        "name": "queue_video",
        "description": "PRIVILEGED. Add a finished video to the daily 8pm auto-post queue. Baadar "
                       "posts one queued video per day automatically to YouTube + FB/IG. Pass the "
                       "local video path, title, description (with links), tags, and a caption.",
        "input_schema": {
            "type": "object",
            "properties": {
                "video_path": {"type": "string"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "tags": {"type": "string"},
                "caption": {"type": "string"},
            },
            "required": ["video_path", "title"],
        },
    },
    {
        "name": "publish_to_youtube",
        "description": "PRIVILEGED. Upload a video to the PIELTS YouTube channel (@pieltsapp) via "
                       "the connected n8n webhook. Pass the local video file path, title, "
                       "description (include pielts.web.app + links), and comma tags. Only call "
                       "after Ajay approves the exact video + title.",
        "input_schema": {
            "type": "object",
            "properties": {
                "video_path": {"type": "string", "description": "local .mp4 path"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "tags": {"type": "string", "description": "comma-separated"},
            },
            "required": ["video_path", "title"],
        },
    },
    {
        "name": "deploy_ielts_site",
        "description": "PRIVILEGED. Rebuild and publish the IELTS app pielts.web.app (regenerates "
                       "sitemap + pre-renders pages for SEO, then deploys). Use after a new blog "
                       "post is published, or when Ajay says 'publish/deploy the IELTS site'.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_social_connections",
        "description": "List which social platforms Ajay has connected and how each one posts "
                       "(browser/n8n/manual). Use this before posting to know where you can publish.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "post_to_all_socials",
        "description": "PRIVILEGED. Publish the SAME approved content to ALL connected social "
                       "platforms at once (or a comma-separated subset like 'facebook,linkedin'). "
                       "Only call after Ajay approved the exact draft. Manual-method platforms "
                       "(e.g. TikTok) are prepared for upload, not auto-posted.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "title": {"type": "string", "description": "for YouTube"},
                "platforms": {"type": "string",
                              "description": "optional comma list; empty = all connected"},
            },
            "required": ["content"],
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
    # --- Email (Gmail) ---
    {
        "name": "check_email",
        "description": "Read Ajay's recent emails (default unread) — sender, subject, "
                       "snippet. Use for 'any emails?', 'check my mail', 'important "
                       "emails today'. `query` uses Gmail search syntax.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "default": "is:unread"},
                "limit": {"type": "integer", "default": 8},
            },
        },
    },
    {
        "name": "send_email",
        "description": "PRIVILEGED. Send an email. Always read the full email back to "
                       "Ajay and get his spoken approval before calling this.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
    },
    # --- Calendar + reminders (fire real alerts) ---
    {
        "name": "add_reminder",
        "description": "Set a reminder that pops a notification at a time. Use for "
                       "'remind me to...', 'don't let me forget...'. `when` examples: "
                       "'5pm', 'today 17:30', 'tomorrow 8am', '2026-06-15 09:00'.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}, "when": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "list_reminders",
        "description": "List Ajay's open reminders.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "todays_events",
        "description": "Read Ajay's calendar events for today / next few days. Use for "
                       "'what's on my calendar', 'am I free', 'ke schedule chha'.",
        "input_schema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "default": 1}},
        },
    },
    {
        "name": "add_event",
        "description": "Add an event to Ajay's calendar. `when` like 'tomorrow 3pm'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "when": {"type": "string"},
                "duration_min": {"type": "integer", "default": 60},
            },
            "required": ["title", "when"],
        },
    },
    # --- Project awareness (knows Ajay's codebases) ---
    {
        "name": "project_overview",
        "description": "Understand one of Ajay's coding projects: its structure, README, "
                       "tech stack, and recent changes. Use when he asks about 'my "
                       "project', 'the IELTS app', 'pielts', what he's building, or "
                       "before helping with its code.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "read_project_file",
        "description": "Read a specific file inside a registered project (relative path).",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "relpath": {"type": "string"}},
            "required": ["name", "relpath"],
        },
    },
    {
        "name": "search_project",
        "description": "Search a project's code for a keyword/function/component.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "query": {"type": "string"}},
            "required": ["name", "query"],
        },
    },
    {
        "name": "list_projects",
        "description": "List the projects Baadar is connected to.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "plan_project_work",
        "description": "Make a concrete step-by-step plan to do something in one of "
                       "Ajay's projects (grounded in its real code). Use for 'plan how "
                       "to add X to pielts', 'how should I build Y'. Read the plan back "
                       "and wait for Ajay before executing.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "goal": {"type": "string"}},
            "required": ["name", "goal"],
        },
    },
    {
        "name": "project_run",
        "description": "PRIVILEGED. Run a shell command inside a project (npm run dev, "
                       "npm run build, git diff, git status…). Confirm before anything "
                       "that changes or deploys.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "command": {"type": "string"}},
            "required": ["name", "command"],
        },
    },
    {
        "name": "project_edit_file",
        "description": "PRIVILEGED. Create or edit a file inside a project (to execute a "
                       "plan step). Read back what you'll change and confirm first; "
                       "changes are git-tracked and reversible.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"}, "relpath": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["name", "relpath", "content"],
        },
    },
    {
        "name": "register_project",
        "description": "PRIVILEGED. Connect Baadar to a new project folder by name + path.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "path": {"type": "string"}},
            "required": ["name", "path"],
        },
    },
    # --- Daily social content studio (IELTS / pielts.web.app) ---
    {
        "name": "make_content",
        "description": "Generate today's full social media content pack — TikTok/Reel "
                       "script, LinkedIn, Facebook, Instagram caption + hashtags — for "
                       "Ajay's IELTS niche and pielts.web.app. Use for 'make today's "
                       "content', 'aaja ko post banau', or with a specific topic.",
        "input_schema": {
            "type": "object",
            "properties": {"topic": {"type": "string"}},
        },
    },
    {
        "name": "todays_content",
        "description": "Show the content pack already generated for today.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "make_video",
        "description": "Create a vertical captioned TikTok/Reel video with Ajay's "
                       "voiceover (free, local, faceless slideshow) from today's or a "
                       "given script. Use for 'make the video', 'video banau'.",
        "input_schema": {
            "type": "object",
            "properties": {"script": {"type": "string"}},
        },
    },
    {
        "name": "send_video_to_phone",
        "description": "Send a video (or today's video) to Ajay's phone via Telegram — "
                       "works on Android (AirDrop doesn't). Use after making a video, or "
                       "for 'send it to my phone'.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "caption": {"type": "string"}},
        },
    },
    {
        "name": "make_flow_prompts",
        "description": "Generate ready-to-paste Google Flow (Veo) SCENE PROMPTS for a Mr Yeti "
                       "IELTS video (6-8 shots, each with action + spoken line). Use for "
                       "'make flow prompts' / 'scene prompts' / 'next video'. Ajay pastes them "
                       "into Google Flow.",
        "input_schema": {
            "type": "object",
            "properties": {"topic": {"type": "string"}},
        },
    },
    {
        "name": "make_talking_yeti",
        "description": "Make a FREE local animated talking Mr. Yeti video (cloned voice + "
                       "Wav2Lip lip-sync) from today's or a given script. No API keys, no "
                       "cost. Use for 'make the talking yeti' / 'make the animated yeti'.",
        "input_schema": {
            "type": "object",
            "properties": {"script": {"type": "string"}},
        },
    },
    {
        "name": "make_animated_video",
        "description": "Make a FULL animated talking Mr.Yeti video via HeyGen (cloud, needs "
                       "paid HeyGen + ElevenLabs keys). Prefer make_talking_yeti (free).",
        "input_schema": {
            "type": "object",
            "properties": {"script": {"type": "string"}},
        },
    },
    {
        "name": "check_animated_video",
        "description": "Check if the HeyGen animated video is done and download it.",
        "input_schema": {
            "type": "object",
            "properties": {"video_id": {"type": "string"}},
            "required": ["video_id"],
        },
    },
    # --- Research + planning ---
    {
        "name": "research",
        "description": "Search the live web and answer with current information. Use "
                       "whenever Ajay asks to research, look up, find out, or anything "
                       "needing fresh facts (prices, news, how-to, comparisons).",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "depth": {"type": "string", "enum": ["quick", "deep"], "default": "quick"},
            },
            "required": ["topic"],
        },
    },
    {
        "name": "deep_plan",
        "description": "Build a researched, step-by-step plan for one of Ajay's goals, "
                       "combining live web research with everything you remember about "
                       "him. Use for 'make me a plan', 'how should I...', business "
                       "decisions, or big tasks.",
        "input_schema": {
            "type": "object",
            "properties": {"goal": {"type": "string"}},
            "required": ["goal"],
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
    {
        "name": "what_learned",
        "description": "List the things Saathi has learned about Ajay from talking with "
                       "him. Use when he asks 'what do you know about me', 'what have you "
                       "learned', 'maile ke sikeko'.",
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
    "list_social_connections": content.list_connections,
    "post_to_all_socials": content.post_all,
    "deploy_ielts_site": content_studio.deploy_ielts_site,
    "publish_to_youtube": content_studio.publish_to_youtube,
    "queue_video": content_studio.queue_video,
    "make_daily_kit": content_studio.make_daily_kit,
    "make_blog_post": content_studio.make_blog_post,
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
    "project_overview": projects.project_overview,
    "read_project_file": projects.read_project_file,
    "search_project": projects.search_project,
    "list_projects": lambda: projects.list_projects(),
    "register_project": projects.register_project,
    "plan_project_work": projects.plan_project_work,
    "project_run": projects.project_run,
    "project_edit_file": projects.project_edit_file,
    "make_content": content_studio.generate_content_pack,
    "todays_content": lambda: content_studio.todays_content(),
    "send_video_to_phone": content_studio.send_today_video,
    "make_video": content_studio.make_video,
    "make_flow_prompts": content_studio.make_flow_prompts,
    "make_talking_yeti": content_studio.make_talking_yeti,
    "make_animated_video": content_studio.make_animated_video,
    "check_animated_video": content_studio.check_heygen_video,
    "check_email": email_tool.check_email,
    "send_email": email_tool.send_email,
    "add_reminder": cal.add_reminder,
    "list_reminders": cal.list_reminders,
    "todays_events": cal.todays_events,
    "add_event": cal.add_event,
    "research": research.research,
    "deep_plan": research.deep_plan,
    "check_messages": apps.check_messages,
    "look_at_screen": apps.look_at_screen,
    "record_feedback": lambda kind, detail="": selfimprove.record_feedback(kind, detail),
    "self_improve": lambda: selfimprove.run_cycle(),
    "self_status": lambda: selfimprove.status(),
    "what_learned": lambda: selfimprove.what_learned(),
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
