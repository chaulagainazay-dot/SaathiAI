from __future__ import annotations
"""
Reddit Outreach for pielts.

Scans r/IELTS and related subreddits for questions where pielts can help.
Drafts helpful, non-spammy replies using the LLM.
Posts replies via PRAW (requires REDDIT_* env vars).

Required .env keys:
  REDDIT_CLIENT_ID      — script-app client id
  REDDIT_CLIENT_SECRET  — script-app secret
  REDDIT_USERNAME       — your Reddit username
  REDDIT_PASSWORD       — your Reddit password
  REDDIT_USER_AGENT     — e.g. "pielts_bot/1.0 by u/YourUsername"
"""

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from .. import config

QUEUE_DIR = config.ROOT / "data" / "reddit_outreach"
QUEUE_DIR.mkdir(parents=True, exist_ok=True)
QUEUE_FILE = QUEUE_DIR / "queue.json"
DAILY_POST_FILE = QUEUE_DIR / "daily_posts.json"

# Subreddits to post daily content to (rotate to avoid spam flags)
POST_SUBREDDITS = [
    {"name": "IELTS",            "flair": None},
    {"name": "EnglishLearning",  "flair": None},
    {"name": "studyabroad",      "flair": None},
]

SUBREDDITS = ["IELTS", "EnglishLearning", "studyabroad"]
SCAN_QUERIES = [
    "site:reddit.com r/IELTS practice app recommend free",
    "site:reddit.com r/IELTS writing task speaking help tool 2024 2025",
    "site:reddit.com r/IELTS band score improve resources",
    "site:reddit.com r/EnglishLearning IELTS preparation online free",
    "site:reddit.com r/studyabroad IELTS score practice help",
]
MAX_QUEUE = 20  # never keep more than 20 pending drafts


# ── Credentials ───────────────────────────────────────────────────────────────

def _creds_ok() -> bool:
    return all(os.environ.get(k) for k in [
        "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET",
        "REDDIT_USERNAME", "REDDIT_PASSWORD",
    ])


def _get_reddit():
    """Return authenticated praw.Reddit instance, or raise if creds missing."""
    import praw
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        username=os.environ["REDDIT_USERNAME"],
        password=os.environ["REDDIT_PASSWORD"],
        user_agent=os.environ.get("REDDIT_USER_AGENT", "pielts_outreach/1.0"),
    )


# ── Post fetching ─────────────────────────────────────────────────────────────

def _exa_search(query: str, n: int = 5) -> str:
    try:
        from .internet_reach import web_search
        r = web_search(query, num_results=n)
        return r.get("output", "") or ""
    except Exception as e:
        return f"[error: {e}]"


def _extract_posts_from_exa(raw: str) -> list[dict]:
    """Parse Exa results to find Reddit post URLs and titles."""
    posts = []
    # Match reddit.com/r/*/comments/* URLs
    pattern = r'(https?://(?:www\.)?reddit\.com/r/\w+/comments/\w+/[^\s"\)\']+)'
    urls = list(dict.fromkeys(re.findall(pattern, raw)))  # dedupe preserving order
    for url in urls[:8]:
        # Extract title from surrounding text (rough heuristic)
        idx = raw.find(url)
        snippet = raw[max(0, idx - 200):idx + 300].strip()
        posts.append({"url": url.rstrip("/"), "snippet": snippet[:400]})
    return posts


def _read_post_via_praw(post_url: str) -> dict | None:
    """Fetch post title + selftext using PRAW (needs credentials)."""
    if not _creds_ok():
        return None
    try:
        r = _get_reddit()
        sub = r.submission(url=post_url)
        sub._fetch()
        return {
            "id": sub.id,
            "title": sub.title,
            "selftext": (sub.selftext or "")[:800],
            "url": post_url,
            "subreddit": str(sub.subreddit),
            "score": sub.score,
            "num_comments": sub.num_comments,
            "already_replied": _has_replied(sub),
        }
    except Exception as e:
        return {"error": str(e), "url": post_url}


def _read_post_via_jina(post_url: str) -> dict | None:
    """Fallback: read post via Jina reader."""
    try:
        r = subprocess.run(
            ["curl", "-sL", "--max-time", "15", f"https://r.jina.ai/{post_url}"],
            capture_output=True, text=True, timeout=20
        )
        text = r.stdout[:1500]
        # Extract title from first heading line
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        title = next((l for l in lines if len(l) > 20 and not l.startswith("[")), "IELTS Question")
        return {
            "id": post_url.split("/comments/")[1].split("/")[0] if "/comments/" in post_url else post_url[-8:],
            "title": title[:200],
            "selftext": text[:600],
            "url": post_url,
            "subreddit": "IELTS",
            "score": 0,
            "num_comments": 0,
            "already_replied": False,
        }
    except Exception:
        return None


def _has_replied(sub) -> bool:
    """Check if we already replied to this post."""
    queue = _load_queue()
    sent_ids = {item["post_id"] for item in queue if item.get("status") == "sent"}
    return sub.id in sent_ids


# ── Draft reply ───────────────────────────────────────────────────────────────

_REPLY_SYSTEM = """You are replying on Reddit as a helpful IELTS community member.
Rules:
- Be genuinely helpful first — answer the actual question
- Mention pielts.web.app ONCE at the end, naturally, only if relevant
- Keep it concise (150-250 words)
- No hype, no exclamation spam, sound like a real person
- Don't start with "I" — vary your opening
- Never say "As an AI"
"""


def _draft_reply(post: dict) -> str:
    from ._llm_helper import ask_llm
    prompt = f"""
Reddit post in r/{post.get('subreddit','IELTS')}:

Title: {post.get('title','')}

Body: {post.get('selftext','(no body — title-only post)')}

Write a helpful Reddit reply. End with a natural mention of pielts.web.app if it fits.
"""
    return ask_llm(prompt, system=_REPLY_SYSTEM, timeout=45).strip()


# ── Queue management ──────────────────────────────────────────────────────────

def _load_queue() -> list[dict]:
    if QUEUE_FILE.exists():
        try:
            return json.loads(QUEUE_FILE.read_text())
        except Exception:
            pass
    return []


def _save_queue(queue: list[dict]):
    QUEUE_FILE.write_text(json.dumps(queue, indent=2, ensure_ascii=False))


def _queue_has(post_id: str) -> bool:
    return any(item["post_id"] == post_id for item in _load_queue())


# ── Main scan pipeline ────────────────────────────────────────────────────────

def scan_and_draft(max_new: int = 8) -> dict:
    """
    1. Exa-search Reddit for fresh IELTS questions
    2. Fetch post details (PRAW if available, else Jina)
    3. Draft LLM reply for each
    4. Save to queue (status=draft)
    Returns summary dict.
    """
    queue = _load_queue()
    added = 0

    for query in SCAN_QUERIES:
        if added >= max_new:
            break
        raw = _exa_search(query, n=5)
        posts_found = _extract_posts_from_exa(raw)
        for pf in posts_found:
            if added >= max_new:
                break
            url = pf["url"]
            # Derive post_id from URL
            m = re.search(r"/comments/(\w+)/", url)
            if not m:
                continue
            post_id = m.group(1)
            if _queue_has(post_id):
                continue

            # Fetch post details
            post = _read_post_via_praw(url) if _creds_ok() else _read_post_via_jina(url)
            if not post or post.get("error") or post.get("already_replied"):
                continue
            post["post_id"] = post_id

            # Draft reply
            print(f"  📝 Drafting reply for: {post.get('title','?')[:60]}…")
            draft = _draft_reply(post)

            queue.append({
                "post_id": post_id,
                "title": post.get("title", ""),
                "subreddit": post.get("subreddit", ""),
                "url": url,
                "score": post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
                "draft": draft,
                "status": "draft",  # draft | sent | skipped
                "scanned_at": datetime.now().isoformat(),
                "sent_at": None,
            })
            added += 1

    # Keep only MAX_QUEUE most recent drafts + all sent/skipped
    drafts = [i for i in queue if i["status"] == "draft"][-MAX_QUEUE:]
    non_drafts = [i for i in queue if i["status"] != "draft"]
    _save_queue(non_drafts + drafts)

    return {"ok": True, "added": added, "total_drafts": len(drafts)}


# ── Post a reply ──────────────────────────────────────────────────────────────

def send_reply(post_id: str, reply_text: str) -> dict:
    """Post reply_text as a comment on the Reddit post identified by post_id."""
    if not _creds_ok():
        return {
            "ok": False,
            "error": "Reddit credentials not configured. Add REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD to .env",
        }
    try:
        r = _get_reddit()
        sub = r.submission(id=post_id)
        comment = sub.reply(reply_text)
        # Mark as sent in queue
        queue = _load_queue()
        for item in queue:
            if item["post_id"] == post_id:
                item["status"] = "sent"
                item["sent_at"] = datetime.now().isoformat()
                item["comment_id"] = comment.id
                break
        _save_queue(queue)
        return {"ok": True, "comment_id": comment.id, "comment_url": f"https://reddit.com{comment.permalink}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def skip_post(post_id: str) -> dict:
    queue = _load_queue()
    for item in queue:
        if item["post_id"] == post_id:
            item["status"] = "skipped"
            break
    _save_queue(queue)
    return {"ok": True}


def update_draft(post_id: str, new_text: str) -> dict:
    queue = _load_queue()
    for item in queue:
        if item["post_id"] == post_id and item["status"] == "draft":
            item["draft"] = new_text
            break
    _save_queue(queue)
    return {"ok": True}


def get_queue(status_filter: str = "draft") -> list[dict]:
    queue = _load_queue()
    if status_filter == "all":
        return queue
    return [i for i in queue if i["status"] == status_filter]


def creds_status() -> dict:
    ok = _creds_ok()
    username = os.environ.get("REDDIT_USERNAME", "")
    return {"configured": ok, "username": username if ok else None}


# ── Daily Reddit post (new submission, not a comment) ─────────────────────────

_POST_SYSTEM = """You write Reddit posts for r/IELTS and similar communities on behalf of an IELTS teacher.

Rules:
- Genuinely helpful — real tips a student can use TODAY
- Reddit-native voice: casual, direct, no corporate speak
- Title: catchy, specific, not clickbait (max 10 words)
- Body: 150-250 words, use Reddit markdown (bullet points, **bold**)
- Mention pielts.web.app once at the very end, naturally
- Never sound like an ad
- Vary the format each day: some days tips list, some days story, some days Q&A style
"""


def draft_daily_submission(cal_post: dict | None = None) -> dict:
    """
    Draft a Reddit post (title + body) from today's content calendar entry.
    Returns { title, body, subreddit, date }.
    """
    from ._llm_helper import ask_llm

    # Pick today's subreddit (rotate day-of-week)
    day_idx = datetime.now().weekday()  # 0=Mon … 6=Sun
    target = POST_SUBREDDITS[day_idx % len(POST_SUBREDDITS)]
    subreddit = target["name"]

    topic = ""
    hook = ""
    if cal_post:
        topic = cal_post.get("core_message") or cal_post.get("hook") or ""
        hook  = cal_post.get("hook") or ""

    prompt = f"""
Today's IELTS content topic: {topic or 'IELTS Writing Task 2 tips'}
Today's hook: {hook or 'How to improve your band score fast'}
Target subreddit: r/{subreddit}

Write a helpful Reddit post (title + body). Return JSON:
{{
  "title": "...",
  "body": "...(markdown, 150-250 words, mention pielts.web.app once at end)..."
}}
Return ONLY valid JSON.
"""
    from ._llm_helper import ask_llm
    raw = ask_llm(prompt, system=_POST_SYSTEM, timeout=45)
    # Robust parse — handle literal newlines inside JSON strings
    data = None
    try:
        import re as _re
        m = _re.search(r'\{[\s\S]*\}', raw)
        if m:
            cleaned = m.group(0).replace('\r', '\\r').replace('\n', '\\n').replace('\t', '\\t')
            # unescape double-escaped sequences that were already correct
            cleaned = cleaned.replace('\\\\n', '\\n').replace('\\\\t', '\\t')
            data = json.loads(cleaned)
    except Exception:
        pass
    if not isinstance(data, dict):
        # fallback: extract title/body with regex
        t = re.search(r'"title"\s*:\s*"([^"]+)"', raw)
        b = re.search(r'"body"\s*:\s*"([\s\S]+?)"(?:\s*[,}])', raw)
        data = {
            "title": t.group(1) if t else f"IELTS tip: {topic[:60]}",
            "body":  b.group(1).replace('\\n', '\n') if b else raw[:500],
        }

    return {
        "title": data.get("title", ""),
        "body": data.get("body", ""),
        "subreddit": subreddit,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "status": "pending",   # pending | posted | skipped
        "created_at": datetime.now().isoformat(),
        "posted_at": None,
        "post_url": None,
    }


def _load_daily_posts() -> list[dict]:
    if DAILY_POST_FILE.exists():
        try:
            return json.loads(DAILY_POST_FILE.read_text())
        except Exception:
            pass
    return []


def _save_daily_posts(posts: list[dict]):
    DAILY_POST_FILE.write_text(json.dumps(posts, indent=2, ensure_ascii=False))


def queue_daily_post(cal_post: dict | None = None) -> dict:
    """Draft today's post and add to daily queue (idempotent — one per day)."""
    posts = _load_daily_posts()
    today = datetime.now().strftime("%Y-%m-%d")
    if any(p["date"] == today for p in posts):
        return {"ok": True, "skipped": True, "reason": "Already queued for today"}
    draft = draft_daily_submission(cal_post)
    posts.append(draft)
    # Keep only last 30 days
    _save_daily_posts(posts[-30:])
    print(f"  📮 Reddit daily post queued: {draft['title'][:60]}")
    return {"ok": True, "draft": draft}


def get_pending_daily_posts() -> list[dict]:
    """Return posts that are pending (not yet posted today)."""
    posts = _load_daily_posts()
    today = datetime.now().strftime("%Y-%m-%d")
    return [p for p in posts if p["date"] == today and p["status"] == "pending"]


def mark_daily_post_sent(date: str, post_url: str = "") -> dict:
    posts = _load_daily_posts()
    for p in posts:
        if p["date"] == date and p["status"] == "pending":
            p["status"] = "posted"
            p["posted_at"] = datetime.now().isoformat()
            p["post_url"] = post_url
            break
    _save_daily_posts(posts)
    return {"ok": True}


def skip_daily_post(date: str) -> dict:
    posts = _load_daily_posts()
    for p in posts:
        if p["date"] == date:
            p["status"] = "skipped"
            break
    _save_daily_posts(posts)
    return {"ok": True}
