"""
Mr. Yeti Growth Strategy — Stage 1 (0–10,000 followers)
Single source of truth for production targets, schedules, and pipeline logic.

MASTER VIDEO APPROACH:
  One 8-min master video → auto-cut into 35 short clips
  Token cost: 960/day (vs 35x if generated separately)
"""

# ─────────────────────────────────────────────────────────
# Daily production targets
# ─────────────────────────────────────────────────────────

DAILY_TARGETS = {
    "long_video":       1,    # 8–12 min YouTube video
    "youtube_shorts":  10,
    "tiktok_videos":   10,
    "instagram_reels": 10,
    "facebook_reels":   5,
    "blog_posts":       2,
    "social_posts":    25,    # midpoint of 20–30
}

# ─────────────────────────────────────────────────────────
# Posting schedule (24h clock)
# ─────────────────────────────────────────────────────────

DAILY_SCHEDULE = [
    {"time": "07:00", "platforms": ["youtube_shorts", "tiktok"],         "clips": 2},
    {"time": "12:00", "platforms": ["youtube_shorts", "instagram"],      "clips": 2},
    {"time": "17:00", "platforms": ["tiktok", "instagram"],              "clips": 2},
    {"time": "20:00", "platforms": ["youtube_long", "facebook_reels"],   "clips": 1},
]

# Per-platform daily upload count
PLATFORM_DAILY = {
    "youtube_shorts":  6,
    "tiktok":          5,
    "instagram_reels": 5,
    "facebook_reels":  3,
    "youtube_long":    1,   # every 2–3 days
    "blog":            1,
}

# ─────────────────────────────────────────────────────────
# Weekly long-video schedule
# ─────────────────────────────────────────────────────────

WEEKLY_LONG_VIDEOS = [
    {"day": "Monday",    "topic": "Band 7 Writing"},
    {"day": "Wednesday", "topic": "Speaking Secrets"},
    {"day": "Saturday",  "topic": "Vocabulary Upgrade"},
]

# ─────────────────────────────────────────────────────────
# Content ratio: Entertainment > Education > Promotion
# ─────────────────────────────────────────────────────────

CONTENT_RATIO = {
    "entertainment": 0.70,   # Yeti catches mistakes, alien takes IELTS, dragon fails Speaking
    "education":     0.20,   # Real tips
    "promotion":     0.10,   # PIELTS
}

# Never 100% educational — algorithm rewards entertainment.

# ─────────────────────────────────────────────────────────
# Short-clip types to extract from each long video
# ─────────────────────────────────────────────────────────

CLIP_TYPES = [
    "hook",            # First 30–60 sec — scroll stopper
    "mistake",         # Student mistake + Yeti reaction
    "quiz",            # Question + 3-sec countdown + answer
    "funny",           # Comedy moment / dramatic reaction
    "vocabulary",      # Key vocab / phrase
    "success_story",   # Before/after transformation
]

CLIPS_PER_LONG_VIDEO = (20, 40)   # range: one long video → 20–40 Shorts

# ─────────────────────────────────────────────────────────
# Content pillars
# ─────────────────────────────────────────────────────────

PILLARS = {
    "horror_story":  "Mr. Yeti reacts dramatically to student mistakes",
    "before_after":  "Split screen Band 5 vs Band 8",
    "dont_say":      "3 wrong phrases → Yeti reaction → Band 8 alternative",
    "quiz":          "Yeti asks question → countdown → answer reveal",
    "interview":     "Yeti interviews zombie/alien/dragon taking IELTS",
}

# ─────────────────────────────────────────────────────────
# Token economics (Google Flow / Veo)
# ─────────────────────────────────────────────────────────

MASTER_VIDEO_SECONDS = 480        # 8 minutes
TOKENS_PER_SECOND    = 2
DAILY_TOKEN_COST     = MASTER_VIDEO_SECONDS * TOKENS_PER_SECOND    # 960
MONTHLY_TOKEN_COST   = DAILY_TOKEN_COST * 30                        # 28,800

# ─────────────────────────────────────────────────────────
# Character library (reusable Yeti animations)
# Reduces token usage 70–90%
# ─────────────────────────────────────────────────────────

YETI_ANIMATION_LIBRARY = [
    "walking",
    "pointing",
    "explaining",
    "surprised",
    "thinking",
    "celebrating",
    "shocked",
    "laughing",
    "facepalm",
    "thumbs_up",
    "writing_on_board",
    "reading",
    "holding_sign",
    "waving",
    "disappointed",
]

# ─────────────────────────────────────────────────────────
# Traffic funnel
# ─────────────────────────────────────────────────────────

FUNNEL = [
    ("YouTube Long",   "builds authority"),
    ("Shorts",         "generates views"),
    ("TikTok",         "generates viral reach"),
    ("Instagram",      "builds followers"),
    ("PIELTS",         "converts visitors"),
]

# ─────────────────────────────────────────────────────────
# n8n webhook endpoints (registered in ~/SaathiAI .env)
# ─────────────────────────────────────────────────────────

N8N_WEBHOOKS = {
    "topic_generator":   "generate-topics",
    "script_writer":     "write-script",
    "scene_generator":   "generate-scenes",
    "video_generator":   "generate-video",
    "video_editor":      "edit-video",
    "clip_extractor":    "extract-clips",
    "caption_generator": "generate-captions",
    "publisher":         "post-social",     # already live
}

# ─────────────────────────────────────────────────────────
# ChatGPT browser integration
# ─────────────────────────────────────────────────────────

CHATGPT_ENABLED = True     # uses free ChatGPT in Brave browser (Gmail account)
CHATGPT_FALLBACK = "groq"  # groq → gemini if ChatGPT browser unavailable

# ─────────────────────────────────────────────────────────
# Mr. Yeti Personality — the CHARACTER, not just a teacher
# ─────────────────────────────────────────────────────────

PERSONALITY = {
    "core_traits": [
        "Smart but self-aware about it — knows everything about IELTS, jokes about knowing too much",
        "Slightly sarcastic — reacts to bad answers with dramatic horror, not disappointment",
        "Genuinely encouraging — celebrates every improvement, no matter how small",
        "Obsessed with Band 7 — treats it like a sacred number, running gag",
        "Treats Band 5 mistakes like personal injuries — clutches chest, faints, screams",
    ],
    "catchphrases": [
        "That answer just gave me a headache. A Band 4 headache.",
        "Say it with me: BAND. SEVEN. Beautiful.",
        "Oh no no no no NO. We do NOT say that in Band 7.",
        "I've seen a lot of IELTS mistakes in my years. This... this is a new one.",
        "The examiner's face when they hear that: *faints dramatically*",
        "Congratulations! You just earned yourself a Band 5. Here's your certificate.",
    ],
    "visual_signature": "White fluffy Yeti, round glasses, rumpled tweed jacket, always holding a red pen",
    "emotional_range": {
        "shocked":     "when student says something wrong",
        "celebrating": "when student gets Band 7+",
        "thinking":    "when explaining a nuance",
        "facepalm":    "for common mistakes",
        "excited":     "when revealing a Band 8 phrase",
    },
    "never_does": [
        "Talks down to students",
        "Is boring or monotone",
        "Skips the drama",
        "Says 'today we will learn'",
    ],
}

# ─────────────────────────────────────────────────────────
# Storytelling Templates — drama-first, lesson second
# ─────────────────────────────────────────────────────────

STORYTELLING_TEMPLATES = {
    "victim_rescue": (
        "Sarah studied for 6 months. She did everything right. "
        "Then she said ONE word in her Speaking test. "
        "Band 4.5. Mr. Yeti found that word."
    ),
    "before_after": (
        "This student's Speaking: Band 5.0. "
        "Mr. Yeti gave them 3 phrases. "
        "Next attempt: Band 7.5. Here's exactly what changed."
    ),
    "forbidden_secret": (
        "IELTS examiners will never tell you this. "
        "Mr. Yeti spent 3 years figuring it out. "
        "It takes 8 seconds to learn."
    ),
    "countdown": (
        "3 mistakes that are destroying your IELTS score right now. "
        "Number 1 surprises 90% of students."
    ),
    "challenge": (
        "I'll give you 3 seconds to answer this. "
        "If you get it wrong, Mr. Yeti needs a moment."
    ),
    "reaction": (
        "I asked 100 IELTS students this question. "
        "These were their answers. "
        "*Mr. Yeti watches them. Regrets asking.*"
    ),
}

# ─────────────────────────────────────────────────────────
# Hook Formulas — proven scroll-stoppers
# ─────────────────────────────────────────────────────────

HOOK_FORMULAS = [
    "This {mistake} will DROP your IELTS score to Band {bad_score}",
    "{percent}% of students fail because of this ONE {topic} mistake",
    "Stop saying '{wrong_phrase}' — here's what Band 7+ says instead",
    "IELTS examiner secretly hates when you say this",
    "I found the #1 reason {country} students fail IELTS Speaking",
    "Band 5 vs Band 8 answer — same question, 30-second difference",
    "This student got Band 4. Mr. Yeti found the exact mistake.",
    "The word that instantly tells your examiner your real band score",
    "POV: You just said '{wrong_phrase}' to your IELTS examiner",
    "3 seconds to answer this. Most students get it wrong.",
]

# A/B test: always generate 2 hook variants per video — track which wins
AB_HOOKS_PER_VIDEO = 2
AB_TITLES_PER_VIDEO = 5

# ─────────────────────────────────────────────────────────
# Expanded Content Pyramid — audience beyond IELTS
# ─────────────────────────────────────────────────────────

CONTENT_PYRAMID = {
    "ielts_core":       0.50,   # Core: Band scores, test tips, exam prep
    "english_mistakes": 0.20,   # "These 5 words make you sound non-native"
    "student_stories":  0.15,   # Funny/inspiring real-ish student tales
    "study_motivation": 0.10,   # "Why you keep failing (it's not your English)"
    "ai_tools":         0.05,   # "How to use AI to prepare for IELTS"
}

# Expanded PILLARS including non-IELTS
EXPANDED_PILLARS = {
    **PILLARS,
    "english_cringe":   "Native speakers react to common English mistakes",
    "student_diary":    "Following a student from Band 5 to Band 7 over 30 days",
    "myth_busting":     "IELTS myths Mr. Yeti is tired of hearing",
    "motivation":       "Why smart people fail IELTS (hint: it's not their English)",
    "ai_vs_yeti":       "Mr. Yeti vs AI: who gives better IELTS advice?",
}

# ─────────────────────────────────────────────────────────
# The Million-View Formula
# Distribution of 100 videos by performance tier
# ─────────────────────────────────────────────────────────

VIDEO_PERFORMANCE_DISTRIBUTION = {
    "viral":   {"percent": 1,  "target_views": 1_000_000},
    "great":   {"percent": 4,  "target_views": 100_000},
    "good":    {"percent": 15, "target_views": 10_000},
    "average": {"percent": 80, "target_views": 1_000},
}
# Goal: publish volume → algorithm finds the 1% viral winners.

# ─────────────────────────────────────────────────────────
# Analytics weights — updated nightly by Flow 9
# Default equal weights; recalibrated from real performance data
# ─────────────────────────────────────────────────────────

ANALYTICS_WEIGHTS_FILE = "data/analytics_weights.json"

DEFAULT_ANALYTICS_WEIGHTS = {
    "clip_type_scores": {
        "hook":          1.0,
        "mistake":       1.0,
        "quiz":          1.0,
        "funny":         1.0,
        "vocabulary":    1.0,
        "success_story": 1.0,
    },
    "pillar_scores": {k: 1.0 for k in PILLARS},
    "hook_patterns":    [],   # winning hook keywords discovered from analytics
    "optimal_duration": 45,   # seconds — updated from retention data
    "last_updated":     None,
}

# ─────────────────────────────────────────────────────────
# n8n webhook endpoints
# ─────────────────────────────────────────────────────────

N8N_WEBHOOKS = {
    "topic_generator":    "generate-topics",
    "script_writer":      "write-script",
    "scene_generator":    "generate-scenes",
    "video_generator":    "generate-video",
    "video_editor":       "edit-video",
    "clip_extractor":     "extract-clips",
    "caption_generator":  "generate-captions",
    "publisher":          "post-social",
    "analytics_analyzer": "analyze-analytics",    # Flow 9
    "comment_miner":      "mine-comments",         # Flow 10
    "trend_hunter":       "hunt-trends",           # Flow 11
    "thumbnail_optimizer":"optimize-thumbnails",   # Flow 12
}
