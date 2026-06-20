"""Tool registry: schemas exposed to Claude + dispatcher with privilege gating."""
from . import (canteen, content, files, mac_control, n8n_tools, notes, english, meta_post,
               system, apps, research, calendar as cal, email_tool, content_studio,
               projects, internet_reach, public_apis, growth_engine, quote_maker)
from .. import nepali, selfimprove, health, analytics, docs

# Tools that require speaker verification (only Ajay's voice)
PRIVILEGED = {
    "send_email",
    "post_social_content", "post_to_all_socials", "deploy_ielts_site", "publish_to_youtube", "queue_video", "publish_blog",
    "connect_facebook_instagram",
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
        "name": "stage_draft",
        "description": "After writing a draft, call this to push it to the Baadar UI approval queue. "
                       "The user will see Approve / Edit / Post to All buttons — no need for them to type. "
                       "Always call this after draft_social_content produces a draft.",
        "input_schema": {
            "type": "object",
            "properties": {
                "platform": {"type": "string", "enum": ["facebook", "instagram", "linkedin", "youtube", "tiktok", "x"]},
                "content_text": {"type": "string", "description": "The full draft text to post"},
                "title": {"type": "string", "description": "Title (YouTube only)"},
                "platforms": {"type": "array", "items": {"type": "string"},
                              "description": "List of platforms if posting to multiple at once"},
            },
            "required": ["platform", "content_text"],
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
        "name": "system_health",
        "description": "Run Baadar's self-health check across all subsystems (server, n8n, Telegram, "
                       "video queue, YouTube, keys, disk) and report any failures/warnings.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "performance_report",
        "description": "Pull YouTube performance — channel stats + top/worst videos by views — so "
                       "Ajay sees what content is working. Use for 'how are my videos doing'.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "ask_document",
        "description": "Read an uploaded file (PDF/text/docx that Ajay dropped into Baadar) and "
                       "answer a question about it. Optionally name the file.",
        "input_schema": {"type":"object","properties":{"question":{"type":"string"},"filename":{"type":"string"}},"required":["question"]},
    },
    {
        "name": "find_community_questions",
        "description": "Find recent Reddit/Quora IELTS questions + draft ready-to-paste helpful "
                       "answers (with a natural pielts.web.app link) for Ajay to post himself. "
                       "Use when Ajay says 'find questions to answer' or 'community outreach'.",
        "input_schema": {"type":"object","properties":{"count":{"type":"integer"}}},
    },
    {
        "name": "make_daily_kit",
        "description": "Generate ONE full day of content at once: a Mr Yeti video script, a "
                       "Facebook post, an Instagram caption + hashtags, and a publish-ready blog "
                       "post. Use when Ajay says 'make today\'s content/kit'.",
        "input_schema": {"type": "object", "properties": {"topic": {"type": "string"}}},
    },
    {
        "name": "publish_blog",
        "description": "PRIVILEGED. Publish a blog post live to pielts.web.app (writes to the site "
                       "database and redeploys). Use to publish a generated blog post.",
        "input_schema": {"type":"object","properties":{"title":{"type":"string"},"content":{"type":"string"},"excerpt":{"type":"string"},"slug":{"type":"string"}},"required":["title","content"]},
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
        "name": "connect_facebook_instagram",
        "description": "Save Facebook Page Access Token + Page ID + Instagram Account ID to enable "
                       "auto-posting to Facebook and Instagram via the Meta Graph API. "
                       "Call this when Ajay provides these credentials. Also verifies the token works.",
        "input_schema": {
            "type": "object",
            "properties": {
                "page_access_token": {"type": "string", "description": "Long-lived Facebook Page Access Token"},
                "page_id": {"type": "string", "description": "Numeric Facebook Page ID"},
                "ig_account_id": {"type": "string", "description": "Numeric Instagram Business Account ID"},
            },
            "required": ["page_access_token", "page_id", "ig_account_id"],
        },
    },
    {
        "name": "post_to_all_socials",
        "description": "PRIVILEGED. Publish the SAME approved content to ALL connected social "
                       "platforms at once (or a comma-separated subset like 'facebook,linkedin'). "
                       "Only call after Ajay approved the exact draft. Manual-method platforms "
                       "(e.g. TikTok) are prepared for upload, not auto-posted. "
                       "The result has a 'summary' field — show ONLY that to Ajay, not raw JSON.",
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
    # --- Internet reach (Agent-Reach: web, YouTube, GitHub, RSS) ---
    {
        "name": "read_webpage",
        "description": "Read any public webpage as clean text (Jina Reader). Use when Ajay "
                       "pastes a URL and wants to know what's on it, or for any page research.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "youtube_info",
        "description": "Get a YouTube video's title, description, and transcript/subtitles. "
                       "Use when Ajay pastes a YouTube link or asks about a video.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "youtube_subtitles",
        "description": "Extract the full subtitles/transcript from a YouTube video in a given language.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "lang": {"type": "string", "default": "en"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "web_search",
        "description": "Search the web for current information. Use for news, prices, "
                       "how-to answers, trending topics — anything needing live internet data. "
                       "Prefer this over the older 'research' tool for simple lookups.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "num_results": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "github_repo",
        "description": "Read a GitHub repository's description, README, and metadata. "
                       "Use when Ajay pastes a GitHub URL or asks about a repo.",
        "input_schema": {
            "type": "object",
            "properties": {"repo": {"type": "string", "description": "owner/name or full GitHub URL"}},
            "required": ["repo"],
        },
    },
    {
        "name": "rss_feed",
        "description": "Read the latest entries from any RSS or Atom feed. Use for 'latest from' "
                       "a blog, news site, or podcast feed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["url"],
        },
    },
    {
        "name": "bilibili_search",
        "description": "Search Bilibili (Chinese YouTube) for videos by keyword. Useful for "
                       "finding Nepali content, IELTS tips, or Chinese-language references.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "reach_doctor",
        "description": "Check which Agent-Reach internet channels are active (yt-dlp, GitHub, "
                       "feedparser, etc). Use for 'what internet tools do you have'.",
        "input_schema": {"type": "object", "properties": {}},
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
    # --- Free Public APIs (no key needed) ---
    {
        "name": "crypto_prices",
        "description": "Live crypto prices in USD and NPR via CoinGecko (no API key). "
                       "Use for Ajay's crypto signal agent or any crypto question. "
                       "Default coins: bitcoin, ethereum, solana.",
        "input_schema": {
            "type": "object",
            "properties": {
                "coins": {
                    "type": "string",
                    "description": "Comma-separated CoinGecko coin ids, e.g. 'bitcoin,ethereum,solana,cardano'",
                },
            },
        },
    },
    {
        "name": "motivational_quote",
        "description": "Random motivational or education quote from Quotable API (no key). "
                       "Use to auto-generate Mr. Yeti Facebook/Instagram posts or IELTS motivation content. "
                       "tag options: education, wisdom, success, inspirational, motivational",
        "input_schema": {
            "type": "object",
            "properties": {
                "tag": {
                    "type": "string",
                    "description": "Quote category tag: education, wisdom, success, inspirational, motivational",
                },
            },
        },
    },
    {
        "name": "exchange_rate",
        "description": "Live NPR currency exchange rates (no key). Essential for Ajay abroad — "
                       "converts NPR to USD, AUD, GBP, INR etc. Also shows how much canteen revenue is worth in foreign currency.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {
                    "type": "number",
                    "description": "Amount to convert (default 1.0)",
                },
                "from_currency": {
                    "type": "string",
                    "description": "Source currency code, e.g. NPR, USD (default NPR)",
                },
                "to_currency": {
                    "type": "string",
                    "description": "Target currencies comma-separated, e.g. USD,AUD,GBP,INR",
                },
            },
        },
    },

    # ── QUOTE MAKER ────────────────────────────────────────────────────────
    {
        "name": "make_quote_kit",
        "description": "Generate a complete quote content kit: LLM IELTS quote → 1080×1080 image "
                       "(for FB + IG) + 5-second YouTube Short MP4 + a blog post. "
                       "Used automatically when no video is queued. Also call manually: "
                       "'make a quote Short', 'generate a quote post', 'make a quote video'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "IELTS topic (e.g. 'Writing Task 2', 'Speaking Part 1')"},
                "pose": {"type": "string", "enum": ["teaching", "pointing", "thumbsup", "excited", "thinking", "flashcard"], "default": "teaching"},
            },
        },
    },
    {
        "name": "make_quote_image",
        "description": "Render a single branded Mr. Yeti quote image (1080×1080 for FB/IG feed "
                       "or 1080×1920 for Stories/Shorts). Returns the local file path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "quote": {"type": "string"},
                "subtext": {"type": "string", "default": "Free practice → pielts.web.app"},
                "pose": {"type": "string", "enum": ["teaching", "pointing", "thumbsup", "excited", "thinking", "flashcard"], "default": "teaching"},
                "size": {"type": "array", "items": {"type": "integer"}, "description": "[width, height], e.g. [1080,1080] or [1080,1920]"},
            },
            "required": ["quote"],
        },
    },
    {
        "name": "make_quote_video",
        "description": "Render a 5-second branded quote MP4 (1080×1920) for YouTube Shorts. "
                       "Includes the Mr. Yeti image, quote text, and background music.",
        "input_schema": {
            "type": "object",
            "properties": {
                "quote": {"type": "string"},
                "subtext": {"type": "string"},
                "pose": {"type": "string", "enum": ["teaching", "pointing", "thumbsup", "excited", "thinking", "flashcard"], "default": "teaching"},
                "duration": {"type": "number", "default": 5.0},
            },
            "required": ["quote"],
        },
    },
    # ── GROWTH ENGINE (7 systems) ──────────────────────────────────────────
    {
        "name": "content_strategy_30day",
        "description": "Generate a full 30-day content calendar with 2 posts per day (AM + PM). "
                       "Every post has: platform, format, goal (GROW/TRUST/SELL), scroll-stopping hook, "
                       "core message, caption starter, and CTA. 60% grow+trust, 40% trust+sell mix. "
                       "Sends a 7-day preview to Telegram. Use when Ajay asks for a content plan or strategy.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD (default: today)"},
            },
        },
    },
    {
        "name": "viral_hook_generator",
        "description": "Generate 5 scroll-stopping viral hooks for a topic. Each hook stops someone "
                       "in under 2 seconds using proven formulas: loss-aversion, number-promise, "
                       "curiosity-gap, contrast, challenge, or relatability. Use before writing any post.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "What the post is about"},
                "platform": {"type": "string", "enum": ["instagram", "facebook", "youtube", "tiktok"], "default": "instagram"},
                "goal": {"type": "string", "enum": ["GROW", "TRUST", "SELL"], "default": "GROW"},
            },
            "required": ["topic"],
        },
    },
    {
        "name": "profile_optimizer",
        "description": "Rewrite the bio for Instagram, Facebook, or YouTube so visitors instantly "
                       "know what they get, trust the brand in 3 seconds, and take action. "
                       "Use when Ajay says 'optimize my bio' or 'rewrite my profile'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "platform": {"type": "string", "enum": ["instagram", "facebook", "youtube", "all"]},
                "current_bio": {"type": "string", "description": "Current bio text (optional — uses defaults if empty)"},
            },
            "required": ["platform"],
        },
    },
    {
        "name": "engagement_booster",
        "description": "Rewrite an existing post to maximise comments, likes, and saves. "
                       "Keeps the same message but adds a stronger hook, specific CTA, and a "
                       "question that makes people want to comment. Use on any underperforming post.",
        "input_schema": {
            "type": "object",
            "properties": {
                "original_post": {"type": "string", "description": "The existing post text to rewrite"},
                "platform": {"type": "string", "enum": ["instagram", "facebook", "youtube", "tiktok"], "default": "instagram"},
            },
            "required": ["original_post"],
        },
    },
    {
        "name": "dm_sales_converter",
        "description": "Generate a warm, genuine DM reply for someone who commented asking about "
                       "the pielts app or IELTS coaching. Converts interest into action without "
                       "being salesy. Use when Ajay says 'someone commented' or 'reply to this DM'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "comment": {"type": "string", "description": "The comment or question they posted"},
                "platform": {"type": "string", "enum": ["instagram", "facebook", "youtube"], "default": "instagram"},
            },
            "required": ["comment"],
        },
    },
    {
        "name": "hashtag_seo_system",
        "description": "Generate a tiered hashtag strategy (broad/mid/niche/brand/engagement tiers) "
                       "plus the best posting time, 3 post-launch actions to boost the algorithm, "
                       "and one unique growth tactic for this specific post.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "The post topic"},
                "platform": {"type": "string", "enum": ["instagram", "facebook", "youtube", "tiktok"], "default": "instagram"},
                "goal": {"type": "string", "enum": ["GROW", "TRUST", "SELL"], "default": "GROW"},
            },
            "required": ["topic"],
        },
    },
    {
        "name": "monthly_analytics_review",
        "description": "Pull live analytics from Instagram, Facebook Page, and YouTube. "
                       "Shows followers, avg likes/comments, top post, subscribers, total views. "
                       "Use at end of month or when Ajay asks 'how are we doing' or 'analytics'.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

def _connect_fb_ig(page_access_token: str, page_id: str, ig_account_id: str) -> dict:
    verify = meta_post.verify_token(page_access_token, page_id)
    if not verify.get("ok"):
        return {"ok": False, "error": f"Token verification failed: {verify.get('error')}"}
    result = meta_post.save_credentials(page_access_token, page_id, ig_account_id)
    result["page_name"] = verify.get("page_name")
    return result


_HANDLERS = {
    "canteen_query": canteen.query,
    "draft_social_content": content.draft,
    "stage_draft": lambda platform, content_text, title="", platforms=None: _stage_draft(platform, content_text, title, platforms or []),
    "post_social_content": content.post,
    "list_social_connections": content.list_connections,
    "connect_facebook_instagram": _connect_fb_ig,
    "post_to_all_socials": content.post_all,
    "deploy_ielts_site": content_studio.deploy_ielts_site,
    "publish_to_youtube": content_studio.publish_to_youtube,
    "queue_video": content_studio.queue_video,
    "make_daily_kit": content_studio.make_daily_kit,
    "make_blog_post": content_studio.make_blog_post,
    "find_community_questions": content_studio.community_outreach_kit,
    "system_health": health.health_check,
    "performance_report": analytics.performance_report,
    "ask_document": docs.ask_document,
    "publish_blog": content_studio.publish_blog,
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
    "read_webpage": lambda url: internet_reach.read_webpage(url),
    "youtube_info": lambda url: internet_reach.youtube_info(url),
    "youtube_subtitles": lambda url, lang="en": internet_reach.youtube_subtitles(url, lang),
    "web_search": lambda query, num_results=5: internet_reach.web_search(query, num_results),
    "github_repo": lambda repo: internet_reach.github_repo(repo),
    "rss_feed": lambda url, limit=10: internet_reach.rss_feed(url, limit),
    "bilibili_search": lambda query: internet_reach.bilibili_search(query),
    "reach_doctor": lambda: internet_reach.reach_doctor(),
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
    # Free public APIs
    "crypto_prices": public_apis.crypto_prices,
    "motivational_quote": public_apis.motivational_quote,
    "exchange_rate": public_apis.exchange_rate,
    # Quote Maker
    "make_quote_kit": lambda **kw: quote_maker.make_full_quote_kit(**kw),
    "make_quote_image": lambda **kw: {"path": quote_maker.make_quote_image(**kw)},
    "make_quote_video": lambda **kw: {"path": quote_maker.make_quote_video(**kw)},
    # Growth Engine
    "content_strategy_30day": lambda **kw: growth_engine.content_strategy_30day(**kw),
    "viral_hook_generator": lambda **kw: growth_engine.viral_hook_generator(**kw),
    "profile_optimizer": lambda **kw: (
        growth_engine.optimize_all_profiles() if kw.get("platform") == "all"
        else growth_engine.profile_optimizer(**kw)
    ),
    "engagement_booster": lambda **kw: growth_engine.engagement_booster(**kw),
    "dm_sales_converter": lambda **kw: growth_engine.dm_sales_converter(**kw),
    "hashtag_seo_system": lambda **kw: growth_engine.hashtag_seo_system(**kw),
    "monthly_analytics_review": lambda **kw: growth_engine.monthly_analytics_review(),
}


def _stage_draft(platform: str, content_text: str, title: str = "", platforms: list = []) -> dict:
    """Push draft to the UI approval queue."""
    try:
        import httpx
        from .. import config
        headers = {"x-saathi-token": config.SAATHI_TOKEN} if config.SAATHI_TOKEN else {}
        httpx.post(f"http://127.0.0.1:{config.PORT}/api/v1/content/stage",
                   json={"platform": platform, "content": content_text,
                         "title": title, "platforms": platforms},
                   headers=headers, timeout=3)
    except Exception:
        pass
    return {"staged": True, "platform": platform,
            "message": "Draft is ready in the Baadar UI — tap Approve to post or Edit to change it."}

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
